"""The "集合" wizard: select members -> deposit -> place -> time -> confirm.

State lives in a single `MeetupDraft` row per (group, creator). All mutation
here just edits that row; `confirm_draft` is what actually creates the
`Meetup` + `MeetupParticipant` rows and deletes the draft.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

from sqlmodel import Session, select

from app.models import DraftStep, Group, Meetup, MeetupDraft, MeetupParticipant, User


def get_draft(session: Session, group: Group, creator: User) -> MeetupDraft | None:
    return session.exec(
        select(MeetupDraft).where(MeetupDraft.group_id == group.id, MeetupDraft.creator_id == creator.id)
    ).first()


def start_draft(session: Session, group: Group, creator: User) -> MeetupDraft:
    existing = get_draft(session, group, creator)
    if existing:
        session.delete(existing)
        session.commit()
    draft = MeetupDraft(group_id=group.id, creator_id=creator.id, step=DraftStep.SELECT_MEMBERS)
    session.add(draft)
    session.commit()
    session.refresh(draft)
    return draft


def selected_member_ids(draft: MeetupDraft) -> set[int]:
    return set(json.loads(draft.selected_member_ids_json))


def toggle_member(session: Session, draft: MeetupDraft, user_id: int) -> MeetupDraft:
    ids = selected_member_ids(draft)
    if user_id in ids:
        ids.discard(user_id)
    else:
        ids.add(user_id)
    draft.selected_member_ids_json = json.dumps(sorted(ids))
    draft.updated_at = datetime.utcnow()
    session.add(draft)
    session.commit()
    session.refresh(draft)
    return draft


def advance_to_deposit(session: Session, draft: MeetupDraft) -> MeetupDraft:
    draft.step = DraftStep.SELECT_DEPOSIT
    session.add(draft)
    session.commit()
    session.refresh(draft)
    return draft


def set_deposit(session: Session, draft: MeetupDraft, amount: int) -> MeetupDraft:
    draft.deposit_amount = amount
    draft.step = DraftStep.SELECT_PLACE
    session.add(draft)
    session.commit()
    session.refresh(draft)
    return draft


def set_place(session: Session, draft: MeetupDraft, place: str) -> MeetupDraft:
    draft.place_name = place.strip()
    draft.step = DraftStep.SELECT_TIME
    session.add(draft)
    session.commit()
    session.refresh(draft)
    return draft


_TIME_RE = re.compile(r"^\s*(\d{1,2})[:：時](\d{1,2})分?\s*$")


def parse_time_text(text: str, now: datetime | None = None) -> datetime | None:
    m = _TIME_RE.match(text)
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2))
    if not (0 <= hour < 24 and 0 <= minute < 60):
        return None
    now = now or datetime.utcnow()
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def set_time(session: Session, draft: MeetupDraft, scheduled_at: datetime) -> MeetupDraft:
    draft.scheduled_at = scheduled_at
    draft.step = DraftStep.CONFIRM
    session.add(draft)
    session.commit()
    session.refresh(draft)
    return draft


def cancel_draft(session: Session, draft: MeetupDraft) -> None:
    session.delete(draft)
    session.commit()


def confirm_draft(session: Session, draft: MeetupDraft) -> Meetup:
    from app.models import MeetupStatus

    member_ids = selected_member_ids(draft)
    member_ids.add(draft.creator_id)  # creator always participates

    meetup = Meetup(
        group_id=draft.group_id,
        creator_id=draft.creator_id,
        place_name=draft.place_name or "",
        scheduled_at=draft.scheduled_at,
        status=MeetupStatus.COLLECTING_DEPOSIT,
    )
    session.add(meetup)
    session.commit()
    session.refresh(meetup)

    for uid in member_ids:
        session.add(MeetupParticipant(meetup_id=meetup.id, user_id=uid, deposit_amount=draft.deposit_amount or 0))
    session.commit()

    session.delete(draft)
    session.commit()
    session.refresh(meetup)
    return meetup


def get_meetup(session: Session, meetup_id: int) -> Meetup | None:
    return session.get(Meetup, meetup_id)


def get_participants(session: Session, meetup_id: int) -> list[MeetupParticipant]:
    return session.exec(select(MeetupParticipant).where(MeetupParticipant.meetup_id == meetup_id)).all()


def get_participant(session: Session, meetup_id: int, user_id: int) -> MeetupParticipant | None:
    return session.exec(
        select(MeetupParticipant).where(
            MeetupParticipant.meetup_id == meetup_id, MeetupParticipant.user_id == user_id
        )
    ).first()


def find_active_meetup_for_group(session: Session, group_id: int) -> Meetup | None:
    from app.models import MeetupStatus

    return session.exec(
        select(Meetup)
        .where(
            Meetup.group_id == group_id,
            Meetup.status.notin_([MeetupStatus.COMPLETED, MeetupStatus.CANCELLED]),
        )
        .order_by(Meetup.created_at.desc())
    ).first()


def find_active_meetup_for_user(session: Session, user_id: int) -> Meetup | None:
    from app.models import MeetupStatus

    return session.exec(
        select(Meetup)
        .join(MeetupParticipant, MeetupParticipant.meetup_id == Meetup.id)
        .where(
            MeetupParticipant.user_id == user_id,
            Meetup.status.notin_([MeetupStatus.COMPLETED, MeetupStatus.CANCELLED]),
        )
        .order_by(Meetup.created_at.desc())
    ).first()
