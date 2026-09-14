"""Background jobs, keyed off wall-clock time rather than user actions:
opening the doubt-prediction phase, flagging no-shows at meetup time, and
enforcing each participant's self-declared arrival deadline.

Jobs are persisted in the same SQLite file (APScheduler's SQLAlchemyJobStore)
so they survive a process restart.
"""
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings

scheduler = BackgroundScheduler(jobstores={"default": SQLAlchemyJobStore(url=settings.database_url)})


def start() -> None:
    if not scheduler.running:
        scheduler.start()


# --- job bodies -----------------------------------------------------------
# Each job opens its own DB session since it runs outside any request/event.

def _job_open_doubt_phase(meetup_id: int) -> None:
    from app.database import get_session
    from app.models import Meetup, MeetupStatus
    from app.services import deposit_service, doubt_service, meetup_service

    with get_session() as session:
        meetup = session.get(Meetup, meetup_id)
        if not meetup or meetup.doubt_job_fired:
            return
        meetup.doubt_job_fired = True
        session.add(meetup)
        session.commit()

        participants = meetup_service.get_participants(session, meetup_id)
        if meetup.status != MeetupStatus.DOUBT_PHASE:
            # deposits weren't all collected in time; nothing to predict on.
            if not deposit_service.all_deposits_ready(participants):
                return
            meetup.status = MeetupStatus.DOUBT_PHASE
            session.add(meetup)
            session.commit()
        doubt_service.open_doubt_phase(session, meetup, participants)


def _job_flag_late(meetup_id: int) -> None:
    from app.database import get_session
    from app.models import Meetup, MeetupStatus
    from app.services import meetup_service, penalty_service

    with get_session() as session:
        meetup = session.get(Meetup, meetup_id)
        if not meetup or meetup.deadline_job_fired:
            return
        meetup.deadline_job_fired = True
        meetup.status = MeetupStatus.ACTIVE
        session.add(meetup)
        session.commit()

        participants = meetup_service.get_participants(session, meetup_id)
        penalty_service.flag_late_participants(session, meetup, participants)
        penalty_service.maybe_settle(session, meetup)  # in case everyone already arrived early


def _job_enforce_deadline(participant_id: int) -> None:
    from app.database import get_session
    from app.models import Meetup, MeetupParticipant
    from app.services import penalty_service

    with get_session() as session:
        participant = session.get(MeetupParticipant, participant_id)
        if not participant or participant.declared_deadline_job_fired:
            return
        participant.declared_deadline_job_fired = True
        session.add(participant)
        session.commit()

        meetup = session.get(Meetup, participant.meetup_id)
        penalty_service.enforce_declared_deadline(session, meetup, participant)


# --- scheduling entry points ----------------------------------------------

def schedule_meetup_jobs(meetup_id: int, scheduled_at) -> None:
    from datetime import timedelta

    doubt_at = scheduled_at - timedelta(minutes=settings.doubt_phase_minutes_before)
    scheduler.add_job(
        _job_open_doubt_phase, "date", run_date=doubt_at, args=[meetup_id],
        id=f"doubt-{meetup_id}", replace_existing=True, misfire_grace_time=None,
    )
    scheduler.add_job(
        _job_flag_late, "date", run_date=scheduled_at, args=[meetup_id],
        id=f"deadline-{meetup_id}", replace_existing=True, misfire_grace_time=None,
    )


def schedule_declared_deadline(participant_id: int, deadline_at) -> None:
    scheduler.add_job(
        _job_enforce_deadline, "date", run_date=deadline_at, args=[participant_id],
        id=f"declared-{participant_id}", replace_existing=True, misfire_grace_time=None,
    )
