"""The T-2h "doubt" prediction mini-game.

Every participant privately guesses, for every *other* participant, whether
that person will be late. Predictions are pushed and collected 1:1 (never in
the group), and nothing about who predicted what is ever surfaced back to
the group or to the target - only aggregate rewards are announced at
settlement. See penalty_service.score_doubts for the payout rule.
"""
from sqlmodel import Session, select

from app import flex_messages as fx
from app import line_client
from app.models import DoubtPrediction, Meetup, MeetupParticipant, User


def open_doubt_phase(session: Session, meetup: Meetup, participants: list[MeetupParticipant]) -> None:
    users = {p.user_id: session.get(User, p.user_id) for p in participants}
    for p in participants:
        predictor = users[p.user_id]
        for other in participants:
            if other.user_id == p.user_id:
                continue
            target = users[other.user_id]
            line_client.push(
                predictor.line_user_id,
                [fx.doubt_prediction_flex(meetup.id, target.id, target.display_name)],
            )


def record_prediction(session: Session, meetup_id: int, predictor_id: int, target_id: int, predicted_late: bool) -> None:
    existing = session.exec(
        select(DoubtPrediction).where(
            DoubtPrediction.meetup_id == meetup_id,
            DoubtPrediction.predictor_id == predictor_id,
            DoubtPrediction.target_id == target_id,
        )
    ).first()
    if existing:
        existing.predicted_late = predicted_late
        session.add(existing)
    else:
        session.add(DoubtPrediction(
            meetup_id=meetup_id, predictor_id=predictor_id, target_id=target_id, predicted_late=predicted_late
        ))
    session.commit()


def predictions_for_target(session: Session, meetup_id: int, target_id: int) -> list[DoubtPrediction]:
    return session.exec(
        select(DoubtPrediction).where(
            DoubtPrediction.meetup_id == meetup_id, DoubtPrediction.target_id == target_id
        )
    ).all()
