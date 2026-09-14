from sqlmodel import Session

from app import flex_messages as fx
from app import line_client, payments
from app.models import DepositStatus, Meetup, MeetupParticipant, MeetupStatus, User


def request_all_deposits(session: Session, meetup: Meetup, participants: list[MeetupParticipant]) -> None:
    for p in participants:
        user = session.get(User, p.user_id)
        request_deposit(session, meetup, p, user)


def request_deposit(session: Session, meetup: Meetup, participant: MeetupParticipant, user: User) -> None:
    if participant.deposit_amount <= 0:
        participant.deposit_status = DepositStatus.AUTHORIZED
        session.add(participant)
        session.commit()
        return

    result = payments.hold_deposit(user, participant.deposit_amount, meetup.id, participant.id)
    session.add(user)  # picks up a freshly-created stripe_customer_id, if any

    if result.status == "authorized":
        participant.deposit_status = DepositStatus.AUTHORIZED
        participant.deposit_intent_id = result.intent_id
        session.add(participant)
        session.commit()
        line_client.push(user.line_user_id, [fx.text(
            f"「{meetup.place_name}」のデポジット ¥{participant.deposit_amount} を確保しました。"
        )])
    elif result.status == "requires_action":
        session.commit()
        line_client.push(user.line_user_id, [fx.checkout_link_message(result.checkout_url, "デポジット")])
    else:
        participant.deposit_status = DepositStatus.FAILED
        session.add(participant)
        session.commit()
        line_client.push(user.line_user_id, [fx.text("デポジットの確保に失敗しました。カード情報をご確認ください。")])


def all_deposits_ready(participants: list[MeetupParticipant]) -> bool:
    return all(p.deposit_status == DepositStatus.AUTHORIZED for p in participants)


def activate_if_ready(session: Session, meetup: Meetup, participants: list[MeetupParticipant]) -> bool:
    """Move DOUBT_PHASE-eligible meetup forward once every deposit is held."""
    if meetup.status != MeetupStatus.COLLECTING_DEPOSIT:
        return False
    if not all_deposits_ready(participants):
        return False
    meetup.status = MeetupStatus.DOUBT_PHASE
    session.add(meetup)
    session.commit()
    return True
