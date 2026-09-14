from datetime import datetime, timedelta

from app.models import (
    DepositStatus,
    Group,
    Meetup,
    MeetupParticipant,
    MeetupStatus,
    User,
)
from app.services import penalty_service


def _make_meetup_with_participants(session, deposit=1000):
    group = Group(line_group_id="G1")
    session.add(group)
    session.commit()
    session.refresh(group)

    users = []
    for i in range(3):
        u = User(line_user_id=f"U{i}", display_name=f"user{i}")
        session.add(u)
        users.append(u)
    session.commit()
    for u in users:
        session.refresh(u)

    meetup = Meetup(
        group_id=group.id, creator_id=users[0].id, place_name="Shibuya",
        scheduled_at=datetime.utcnow(), status=MeetupStatus.ACTIVE,
    )
    session.add(meetup)
    session.commit()
    session.refresh(meetup)

    participants = []
    for u in users:
        p = MeetupParticipant(meetup_id=meetup.id, user_id=u.id, deposit_amount=deposit,
                                deposit_status=DepositStatus.AUTHORIZED,
                                deposit_intent_id=f"pi_dummy_{u.id}")
        session.add(p)
        participants.append(p)
    session.commit()
    for p in participants:
        session.refresh(p)

    return meetup, users, participants


def test_on_time_everyone_no_payout(session):
    meetup, users, participants = _make_meetup_with_participants(session)
    for p in participants:
        p.arrived_at = datetime.utcnow()
        session.add(p)
    session.commit()

    penalty_service._settle(session, meetup, participants)

    for p in participants:
        session.refresh(p)
        assert p.payout_amount == 0
        assert p.deposit_status == DepositStatus.RELEASED
    assert meetup.status == MeetupStatus.COMPLETED


def test_late_participant_deposit_and_penalty_split_among_others(session):
    meetup, users, participants = _make_meetup_with_participants(session, deposit=900)
    on_time_a, on_time_b, late_c = participants

    on_time_a.arrived_at = datetime.utcnow()
    on_time_b.arrived_at = datetime.utcnow()
    session.add_all([on_time_a, on_time_b])

    late_c.is_late = True
    late_c.deposit_status = DepositStatus.CAPTURED  # forfeited
    late_c.penalty_amount = 900  # missed declared deadline too
    late_c.penalty_status = "charged"
    session.add(late_c)
    session.commit()

    penalty_service._settle(session, meetup, participants)

    session.refresh(on_time_a)
    session.refresh(on_time_b)
    session.refresh(late_c)

    # pot = 900 (deposit) + 900 (penalty) = 1800; no correct doubters -> full
    # 1800 split between the 2 on-time participants = 900 each.
    assert on_time_a.payout_amount == 900
    assert on_time_b.payout_amount == 900
    assert late_c.payout_amount == 0
    assert meetup.status == MeetupStatus.COMPLETED


def test_correct_doubt_prediction_earns_bonus_share(session):
    from app.models import DoubtPrediction

    meetup, users, participants = _make_meetup_with_participants(session, deposit=1000)
    on_time_a, on_time_b, late_c = participants

    on_time_a.arrived_at = datetime.utcnow()
    on_time_b.arrived_at = datetime.utcnow()
    session.add_all([on_time_a, on_time_b])

    late_c.is_late = True
    late_c.deposit_status = DepositStatus.CAPTURED
    session.add(late_c)

    # Only on_time_a correctly predicted late_c would be late.
    session.add(DoubtPrediction(
        meetup_id=meetup.id, predictor_id=on_time_a.user_id, target_id=late_c.user_id, predicted_late=True,
    ))
    session.add(DoubtPrediction(
        meetup_id=meetup.id, predictor_id=on_time_b.user_id, target_id=late_c.user_id, predicted_late=False,
    ))
    session.commit()

    penalty_service._settle(session, meetup, participants)

    session.refresh(on_time_a)
    session.refresh(on_time_b)

    # pot = 1000; bonus pool = 10% = 100, all to on_time_a (sole correct doubter).
    # remaining 900 split between the 2 non-late participants = 450 each.
    assert on_time_a.payout_amount == 100 + 450
    assert on_time_b.payout_amount == 450


def test_declared_deadline_arrival_in_time_forfeits_nothing(session):
    meetup, users, participants = _make_meetup_with_participants(session)
    a, b, c = participants
    a.arrived_at = datetime.utcnow()
    b.arrived_at = datetime.utcnow()

    c.is_late = True
    c.declared_minutes = 10
    c.declared_deadline_at = datetime.utcnow() + timedelta(minutes=10)
    session.add_all([a, b, c])
    session.commit()

    # c arrives before the declared deadline; the scheduler job that would
    # otherwise fire at the deadline must be a no-op once arrived_at is set.
    c.arrived_at = datetime.utcnow()
    session.add(c)
    session.commit()
    penalty_service.enforce_declared_deadline(session, meetup, c)
    session.refresh(c)
    assert c.deposit_status != DepositStatus.CAPTURED
