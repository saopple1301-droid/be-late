import logging

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import LocationMessageContent, MessageEvent, PostbackEvent, TextMessageContent
from sqlmodel import select

from app import line_client, payments, scheduler
from app.api import router as api_router
from app.config import settings
from app.database import get_session, init_db
from app.handlers.message_handler import handle_message
from app.handlers.postback_handler import handle_postback
from app.models import DepositStatus, MeetupParticipant, MeetupStatus, User
from app.services import deposit_service, meetup_service

logger = logging.getLogger("be_late")

app = FastAPI(title="Be Late")

_origins = ["*"] if settings.cors_allow_origins == "*" else [
    o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    scheduler.start()


@app.post("/callback")
async def line_callback(request: Request, x_line_signature: str = Header(default="")):
    body = await request.body()
    try:
        events = line_client.parser.parse(body.decode("utf-8"), x_line_signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="invalid signature")

    for event in events:
        try:
            if isinstance(event, MessageEvent) and isinstance(
                event.message, (TextMessageContent, LocationMessageContent)
            ):
                handle_message(event)
            elif isinstance(event, PostbackEvent):
                handle_postback(event)
        except Exception:
            logger.exception("failed to handle LINE event")

    return "OK"


@app.post("/stripe/webhook")
async def stripe_webhook(request: Request, stripe_signature: str = Header(default="")):
    payload = await request.body()
    try:
        event = payments.construct_webhook_event(payload, stripe_signature)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid stripe signature")

    if event["type"] == "checkout.session.completed":
        _handle_checkout_completed(event["data"]["object"])

    return {"received": True}


def _handle_checkout_completed(session_obj: dict) -> None:
    metadata = session_obj.get("metadata") or {}
    purpose = metadata.get("purpose")
    kind = metadata.get("kind")

    with get_session() as db:
        if session_obj.get("mode") == "setup" or purpose == "card_setup":
            customer_id, pm_id = payments.save_default_payment_method_from_setup_session(session_obj["id"])
            user = db.exec(select(User).where(User.stripe_customer_id == customer_id)).first()
            if not user:
                return
            user.default_payment_method_id = pm_id
            db.add(user)
            db.commit()
            _retry_pending_deposits(db, user)
            return

        if kind in ("deposit", "penalty"):
            participant_id = int(metadata["participant_id"])
            participant = db.get(MeetupParticipant, participant_id)
            if not participant:
                return
            payment_intent_id = session_obj.get("payment_intent")
            if kind == "deposit":
                participant.deposit_status = DepositStatus.AUTHORIZED
                participant.deposit_intent_id = payment_intent_id
            else:
                participant.penalty_status = "charged"
                participant.penalty_intent_id = payment_intent_id
                participant.penalty_amount = participant.deposit_amount
            db.add(participant)
            db.commit()

            if kind == "deposit":
                meetup = meetup_service.get_meetup(db, participant.meetup_id)
                participants = meetup_service.get_participants(db, meetup.id)
                if meetup.status == MeetupStatus.COLLECTING_DEPOSIT:
                    deposit_service.activate_if_ready(db, meetup, participants)


def _retry_pending_deposits(db, user: User) -> None:
    from sqlmodel import select

    pending = db.exec(
        select(MeetupParticipant).where(
            MeetupParticipant.user_id == user.id,
            MeetupParticipant.deposit_status.in_([DepositStatus.PENDING, DepositStatus.FAILED]),
        )
    ).all()
    for participant in pending:
        meetup = meetup_service.get_meetup(db, participant.meetup_id)
        if not meetup or meetup.status != MeetupStatus.COLLECTING_DEPOSIT:
            continue
        deposit_service.request_deposit(db, meetup, participant, user)


@app.get("/stripe/setup-return", response_class=HTMLResponse)
def setup_return() -> str:
    return "<html><body><p>カードの登録が完了しました。LINEに戻ってください。</p></body></html>"


@app.get("/stripe/pay-return", response_class=HTMLResponse)
def pay_return() -> str:
    return "<html><body><p>お支払いが完了しました。LINEに戻ってください。</p></body></html>"


@app.get("/cancel", response_class=HTMLResponse)
def cancel() -> str:
    return "<html><body><p>手続きがキャンセルされました。</p></body></html>"


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
