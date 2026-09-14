"""Stripe integration.

Design notes (read this before wiring real money):

- Deposits are held with a manual-capture PaymentIntent: the card is
  authorized for `deposit_amount` up front but not charged. If everyone is
  on time we *cancel* the authorization (`release_deposit`); if someone is
  late we *capture* it (`capture_deposit`), which is when the money actually
  moves.
- Late-arrival penalties (missing the self-declared "何分以内に到着するか"
  deadline) are separate, auto-captured PaymentIntents charged on top.
- Both flows prefer an off-session charge against the user's saved default
  payment method (collected once via a Stripe Checkout Session in `setup`
  mode - see `create_card_setup_checkout_url`). If there's no saved method,
  or the off-session charge is refused (e.g. `authentication_required`), we
  fall back to a Checkout Session in `payment` mode with
  `payment_intent_data.capture_method` set accordingly, and send the user
  the hosted checkout URL to complete manually.
- Paying *out* the forfeited money to the other members uses Stripe Connect
  transfers (`payout_member`). This requires each recipient to have
  onboarded a connected account (`stripe_account_id`). Students who haven't
  done that simply get `payout_status="manual_required"` recorded, so the
  group can settle up outside the app - the app never guesses at moving
  money to an account it hasn't verified.
"""
from __future__ import annotations

from typing import Optional

import stripe

from app.config import settings
from app.models import User

stripe.api_key = settings.stripe_secret_key


def _customer_id(user: User) -> str:
    if user.stripe_customer_id:
        return user.stripe_customer_id
    customer = stripe.Customer.create(
        name=user.display_name or None,
        metadata={"line_user_id": user.line_user_id},
    )
    user.stripe_customer_id = customer["id"]
    return customer["id"]


def ensure_customer(user: User) -> str:
    """Idempotently create/return the Stripe Customer for a user.

    Caller is responsible for persisting `user` afterwards (this only
    mutates the in-memory object).
    """
    return _customer_id(user)


def create_card_setup_checkout_url(user: User, return_path: str) -> str:
    """Hosted Stripe Checkout (mode=setup) URL to save a card on file.

    LINE can't collect card numbers directly, so we hand the user a link.
    `return_path` is appended to PUBLIC_BASE_URL for the success redirect.
    """
    customer_id = _customer_id(user)
    session = stripe.checkout.Session.create(
        mode="setup",
        customer=customer_id,
        payment_method_types=["card"],
        success_url=f"{settings.public_base_url}{return_path}?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{settings.public_base_url}/cancel",
        metadata={"line_user_id": user.line_user_id, "purpose": "card_setup"},
    )
    return session["url"]


def save_default_payment_method_from_setup_session(session_id: str) -> tuple[str, str]:
    """Returns (customer_id, payment_method_id) after a setup Checkout completes."""
    session = stripe.checkout.Session.retrieve(session_id)
    setup_intent = stripe.SetupIntent.retrieve(session["setup_intent"])
    pm_id = setup_intent["payment_method"]
    stripe.Customer.modify(
        session["customer"],
        invoice_settings={"default_payment_method": pm_id},
    )
    return session["customer"], pm_id


class ChargeResult:
    def __init__(self, status: str, intent_id: Optional[str] = None, checkout_url: Optional[str] = None):
        self.status = status  # "authorized" | "captured" | "requires_action" | "failed"
        self.intent_id = intent_id
        self.checkout_url = checkout_url


def _off_session_intent(user: User, amount: int, capture_method: str, metadata: dict) -> ChargeResult:
    customer_id = _customer_id(user)
    if not user.default_payment_method_id:
        return _checkout_fallback(user, amount, capture_method, metadata)
    try:
        intent = stripe.PaymentIntent.create(
            amount=amount,
            currency=settings.currency,
            customer=customer_id,
            payment_method=user.default_payment_method_id,
            off_session=True,
            confirm=True,
            capture_method=capture_method,
            metadata=metadata,
        )
        status = "authorized" if capture_method == "manual" else "captured"
        return ChargeResult(status=status, intent_id=intent["id"])
    except stripe.error.CardError:
        return _checkout_fallback(user, amount, capture_method, metadata)


def _checkout_fallback(user: User, amount: int, capture_method: str, metadata: dict) -> ChargeResult:
    customer_id = _customer_id(user)
    session = stripe.checkout.Session.create(
        mode="payment",
        customer=customer_id,
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": settings.currency,
                "product_data": {"name": metadata.get("description", "Be Late")},
                "unit_amount": amount,
            },
            "quantity": 1,
        }],
        payment_intent_data={"capture_method": capture_method, "metadata": metadata},
        success_url=f"{settings.public_base_url}/stripe/pay-return?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{settings.public_base_url}/cancel",
        metadata=metadata,
    )
    return ChargeResult(status="requires_action", checkout_url=session["url"])


def hold_deposit(user: User, amount: int, meetup_id: int, participant_id: int) -> ChargeResult:
    return _off_session_intent(
        user,
        amount,
        capture_method="manual",
        metadata={
            "kind": "deposit",
            "meetup_id": str(meetup_id),
            "participant_id": str(participant_id),
            "description": "待ち合わせデポジット",
        },
    )


def charge_penalty(user: User, amount: int, meetup_id: int, participant_id: int) -> ChargeResult:
    return _off_session_intent(
        user,
        amount,
        capture_method="automatic",
        metadata={
            "kind": "penalty",
            "meetup_id": str(meetup_id),
            "participant_id": str(participant_id),
            "description": "遅刻ペナルティ",
        },
    )


def capture_deposit(intent_id: str) -> None:
    stripe.PaymentIntent.capture(intent_id)


def release_deposit(intent_id: str) -> None:
    intent = stripe.PaymentIntent.retrieve(intent_id)
    if intent["status"] in ("requires_capture",):
        stripe.PaymentIntent.cancel(intent_id)
    # already captured/canceled/refunded: nothing to do


def payout_member(user: User, amount: int, meetup_id: int) -> str:
    """Returns 'transferred' or 'manual_required'."""
    if not user.stripe_account_id or amount <= 0:
        return "manual_required"
    try:
        stripe.Transfer.create(
            amount=amount,
            currency=settings.currency,
            destination=user.stripe_account_id,
            transfer_group=f"meetup_{meetup_id}",
        )
        return "transferred"
    except stripe.error.StripeError:
        return "manual_required"


def construct_webhook_event(payload: bytes, sig_header: str):
    return stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
