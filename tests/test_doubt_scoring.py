from datetime import datetime

from app.models import DoubtPrediction, Group, Meetup, MeetupParticipant, MeetupStatus, User
from app.services import doubt_service, penalty_service


def _setup(session):
    group = Group(line_group_id="G1")
    session.add(group)
    session.commit()
    session.refresh(group)

    users = [User(line_user_id=f"U{i}", display_name=f"user{i}") for i in range(4)]
    session.add_all(users)
    session.commit()
    for u in users:
        session.refresh(u)

    meetup = Meetup(group_id=group.id, creator_id=users[0].id, place_name="X",
                     scheduled_at=datetime.utcnow(), status=MeetupStatus.DOUBT_PHASE)
    session.add(meetup)
    session.commit()
    session.refresh(meetup)

    participants = [MeetupParticipant(meetup_id=meetup.id, user_id=u.id, deposit_amount=1000) for u in users]
    session.add_all(participants)
    session.commit()
    for p in participants:
        session.refresh(p)

    return meetup, users, participants


def test_record_prediction_is_upsert(session):
    meetup, users, participants = _setup(session)
    doubt_service.record_prediction(session, meetup.id, users[0].id, users[1].id, True)
    doubt_service.record_prediction(session, meetup.id, users[0].id, users[1].id, False)

    rows = doubt_service.predictions_for_target(session, meetup.id, users[1].id)
    assert len(rows) == 1
    assert rows[0].predicted_late is False


def test_only_correct_late_predictions_are_rewarded(session):
    meetup, users, participants = _setup(session)
    target = participants[3]
    target.is_late = True
    session.add(target)

    # predictor 0: correctly doubted (predicted late, target was late) -> rewarded
    session.add(DoubtPrediction(meetup_id=meetup.id, predictor_id=users[0].id, target_id=target.user_id,
                                  predicted_late=True))
    # predictor 1: wrongly predicted on-time -> not rewarded
    session.add(DoubtPrediction(meetup_id=meetup.id, predictor_id=users[1].id, target_id=target.user_id,
                                  predicted_late=False))
    # predictor 2: also correctly doubted -> shares the reward with predictor 0
    session.add(DoubtPrediction(meetup_id=meetup.id, predictor_id=users[2].id, target_id=target.user_id,
                                  predicted_late=True))
    session.commit()

    handed_out, rewarded = penalty_service.score_doubts(session, meetup.id, target, bonus_pool=100)

    assert handed_out == 100  # 100 // 2 correct doubters * 2 == 100
    assert {r.predictor_id for r in rewarded} == {users[0].id, users[2].id}
    for r in rewarded:
        assert r.reward_amount == 50


def test_no_correct_doubters_hands_out_nothing(session):
    meetup, users, participants = _setup(session)
    target = participants[3]
    target.is_late = True
    session.add(target)
    session.add(DoubtPrediction(meetup_id=meetup.id, predictor_id=users[0].id, target_id=target.user_id,
                                  predicted_late=False))
    session.commit()

    handed_out, rewarded = penalty_service.score_doubts(session, meetup.id, target, bonus_pool=100)
    assert handed_out == 0
    assert rewarded == []


def test_predicting_late_for_someone_who_is_on_time_is_not_rewarded(session):
    meetup, users, participants = _setup(session)
    target = participants[3]
    target.is_late = False  # arrived on time after all
    session.add(target)
    session.add(DoubtPrediction(meetup_id=meetup.id, predictor_id=users[0].id, target_id=target.user_id,
                                  predicted_late=True))
    session.commit()

    handed_out, rewarded = penalty_service.score_doubts(session, meetup.id, target, bonus_pool=100)
    assert handed_out == 0
    assert rewarded == []
