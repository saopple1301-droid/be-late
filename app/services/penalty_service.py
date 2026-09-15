"""Arrival tracking, lateness penalties, and end-of-meetup settlement.

Money flow summary for one meetup:
  1. Everyone's deposit is authorized (held, not charged) up front.
  2. At the scheduled time, anyone not yet arrived is flagged `is_late` and
     asked to declare how many minutes they need.
  3. If they arrive within their declared window: their deposit is simply
     *released* (never charged) - being briefly late costs nothing extra
     beyond having been the reason everyone else had to keep standing
     around, which the group already tolerated by giving them the window.
  4. If they blow through their own declared window too: their deposit is
     *captured* (forfeited) AND an extra penalty charge of the same amount
     is placed. Both amounts are pooled and redistributed to the other
     participants once every participant is resolved (arrived, or
     penalized) - see `_settle`.
  5. A slice of each forfeited pot is carved out as a reward for members who
     correctly "doubted" (predicted late) that person in the pre-meetup
     doubt phase - see `score_doubts`.
"""
from __future__ import annotations

from datetime import datetime

from sqlmodel import Session, select

from app import flex_messages as fx
from app import line_client, payments, scheduler
from app.models import (
    DepositStatus,
    DoubtPrediction,
    Meetup,
    MeetupParticipant,
    MeetupStatus,
    User,
)

DOUBT_BONUS_RATE = 0.10


def mark_arrived(session: Session, meetup: Meetup, participant: MeetupParticipant) -> None:
    if participant.arrived_at:
        return
    participant.arrived_at = datetime.utcnow()
    session.add(participant)
    session.commit()
    maybe_settle(session, meetup)


def flag_late_participants(session: Session, meetup: Meetup, participants: list[MeetupParticipant]) -> None:
    """Called by the scheduler right at `meetup.scheduled_at`."""
    for p in participants:
        if p.arrived_at or p.is_late:
            continue
        p.is_late = True
        session.add(p)
        session.commit()
        user = session.get(User, p.user_id)
        line_client.push(user.line_user_id, [fx.late_notice_message(meetup.id, meetup.place_name)])


def declare_late(session: Session, meetup: Meetup, participant: MeetupParticipant, minutes: int) -> None:
    from datetime import timedelta

    participant.declared_minutes = minutes
    participant.declared_deadline_at = datetime.utcnow() + timedelta(minutes=minutes)
    participant.declared_deadline_job_fired = False
    session.add(participant)
    session.commit()
    scheduler.schedule_declared_deadline(participant.id, participant.declared_deadline_at)

    user = session.get(User, participant.user_id)
    line_client.push(user.line_user_id, [fx.late_declared_ack(minutes)])
    _notify_others(session, meetup, exclude_user_id=participant.user_id,
                    message=fx.group_late_announcement(user.display_name, minutes))


def enforce_declared_deadline(session: Session, meetup: Meetup, participant: MeetupParticipant) -> None:
    """Called by the scheduler at `participant.declared_deadline_at`."""
    if participant.arrived_at:
        return  # made it in time, nothing to do

    user = session.get(User, participant.user_id)

    if participant.deposit_status == DepositStatus.AUTHORIZED and participant.deposit_intent_id:
        payments.capture_deposit(participant.deposit_intent_id)
    participant.deposit_status = DepositStatus.CAPTURED

    if participant.deposit_amount > 0:
        _notify_others(session, meetup, exclude_user_id=participant.user_id,
                        message=fx.deposit_forfeited_announcement(user.display_name, participant.deposit_amount))

        result = payments.charge_penalty(user, participant.deposit_amount, meetup.id, participant.id)
        participant.penalty_amount = participant.deposit_amount
        participant.penalty_status = "charged"
        participant.penalty_intent_id = result.intent_id
        _notify_others(session, meetup, exclude_user_id=participant.user_id,
                        message=fx.penalty_charged_announcement(user.display_name, participant.penalty_amount))

    session.add(participant)
    session.commit()
    maybe_settle(session, meetup)


def _notify_others(session: Session, meetup: Meetup, exclude_user_id: int, message) -> None:
    participants = session.exec(
        select(MeetupParticipant).where(MeetupParticipant.meetup_id == meetup.id)
    ).all()
    for p in participants:
        if p.user_id == exclude_user_id:
            continue
        user = session.get(User, p.user_id)
        line_client.push(user.line_user_id, [message])


def _is_resolved(p: MeetupParticipant) -> bool:
    if p.arrived_at:
        return True
    if p.is_late and p.declared_deadline_at and p.declared_deadline_at <= datetime.utcnow():
        return True
    return False


def maybe_settle(session: Session, meetup: Meetup) -> None:
    participants = session.exec(
        select(MeetupParticipant).where(MeetupParticipant.meetup_id == meetup.id)
    ).all()
    if not all(_is_resolved(p) for p in participants):
        return
    if meetup.status == MeetupStatus.COMPLETED:
        return
    _settle(session, meetup, participants)


def score_doubts(
    session: Session, meetup_id: int, target: MeetupParticipant, bonus_pool: int
) -> tuple[int, list[DoubtPrediction]]:
    """Rewards correct 'this person will be late' predictions about `target`.

    Returns (amount actually handed out, the DoubtPrediction rows that won a
    reward). Any leftover (no correct doubters) flows back into the general
    redistribution pool.
    """
    predictions = session.exec(
        select(DoubtPrediction).where(
            DoubtPrediction.meetup_id == meetup_id, DoubtPrediction.target_id == target.user_id
        )
    ).all()
    for pred in predictions:
        pred.correct = pred.predicted_late == target.is_late
        session.add(pred)

    correct_doubters = [p for p in predictions if p.predicted_late and target.is_late]
    if not correct_doubters or bonus_pool <= 0:
        session.commit()
        return 0, []

    share = bonus_pool // len(correct_doubters)
    if share <= 0:
        session.commit()
        return 0, []

    for pred in correct_doubters:
        pred.reward_amount = share
        session.add(pred)
    session.commit()
    return share * len(correct_doubters), correct_doubters


def _settle(session: Session, meetup: Meetup, participants: list[MeetupParticipant]) -> None:
    meetup.status = MeetupStatus.SETTLING
    session.add(meetup)
    session.commit()

    late_participants = [p for p in participants if p.is_late]

    for late_p in late_participants:
        pot = (late_p.deposit_amount if late_p.deposit_status == DepositStatus.CAPTURED else 0) + late_p.penalty_amount
        if pot <= 0:
            continue

        bonus_pool = int(pot * DOUBT_BONUS_RATE)
        handed_out, rewarded_predictions = score_doubts(session, meetup.id, late_p, bonus_pool)
        for pred in rewarded_predictions:
            reward_recipient = next(p for p in participants if p.user_id == pred.predictor_id)
            reward_recipient.payout_amount += pred.reward_amount
            session.add(reward_recipient)

        general_pool = pot - handed_out
        recipients = [p for p in participants if p.user_id != late_p.user_id]
        if recipients and general_pool > 0:
            share = general_pool // len(recipients)
            for r in recipients:
                r.payout_amount += share
                session.add(r)

    for p in participants:
        if not p.is_late and p.deposit_status == DepositStatus.AUTHORIZED and p.deposit_intent_id:
            payments.release_deposit(p.deposit_intent_id)
            p.deposit_status = DepositStatus.RELEASED
        session.add(p)
    session.commit()

    summary_lines = []
    for p in participants:
        user = session.get(User, p.user_id)
        if p.payout_amount > 0:
            status = payments.payout_member(user, p.payout_amount, meetup.id)
            p.payout_status = status
            session.add(p)
            summary_lines.append(f"{user.display_name}: +¥{p.payout_amount}（デモ精算）")
        elif p.is_late:
            lost = p.deposit_amount + p.penalty_amount
            summary_lines.append(f"{user.display_name}: -¥{lost}（遅刻）")
        else:
            summary_lines.append(f"{user.display_name}: ±0（時間通り）")
    session.commit()

    meetup.status = MeetupStatus.COMPLETED
    meetup.settled_at = datetime.utcnow()
    session.add(meetup)
    session.commit()

    for p in participants:
        user = session.get(User, p.user_id)
        line_client.push(user.line_user_id, [fx.settlement_summary(summary_lines)])
