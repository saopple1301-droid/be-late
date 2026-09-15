"""Simulated payments for the hackathon demo build.

No real money moves anywhere in this module - every "hold", "capture",
"release", "penalty charge" and "payout" is just an instantly-successful
status flip, so the whole deposit/penalty/settlement flow can be demoed
without a payment processor, cards, or bank accounts.

To wire in a real processor later (Stripe, etc.), replace the bodies of
these functions - the rest of the app (deposit_service, penalty_service,
api.py) only depends on this module's function signatures and the
ChargeResult.status values below, not on how the money actually moves.
"""
from __future__ import annotations

import secrets

from app.models import User


class ChargeResult:
    def __init__(self, status: str, intent_id: str | None = None):
        self.status = status  # "authorized" | "captured"
        self.intent_id = intent_id


def _fake_intent_id() -> str:
    return f"sim_{secrets.token_hex(6)}"


def hold_deposit(user: User, amount: int, meetup_id: int, participant_id: int) -> ChargeResult:
    return ChargeResult(status="authorized", intent_id=_fake_intent_id())


def charge_penalty(user: User, amount: int, meetup_id: int, participant_id: int) -> ChargeResult:
    return ChargeResult(status="captured", intent_id=_fake_intent_id())


def capture_deposit(intent_id: str) -> None:
    pass


def release_deposit(intent_id: str) -> None:
    pass


def payout_member(user: User, amount: int, meetup_id: int) -> str:
    return "settled"
