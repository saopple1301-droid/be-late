"""REST API consumed by the companion PWA (webapp/). Every route is
authenticated via a LIFF ID token (see app/auth.py) and reuses the exact
same service-layer functions the LINE bot handlers call, so a meetup
created from the app behaves identically to one created in a LINE group -
deposits, pushes, scheduler jobs, settlement math, all shared.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app import flex_messages as fx
from app import line_client, payments, scheduler
from app.auth import get_current_user
from app.database import get_session
from app.models import DoubtPrediction, Meetup, MeetupParticipant, MeetupStatus, User
from app.services import deposit_service, doubt_service, identity_service, location_service, meetup_service

router = APIRouter(prefix="/api")


def _session() -> Session:
    with get_session() as s:
        yield s


CurrentUser = Depends(get_current_user)
Db = Depends(_session)


def _require_membership(session: Session, group_id: int, user: User):
    group = identity_service.get_group(session, group_id)
    if not group or not identity_service.is_member(session, group, user):
        raise HTTPException(status_code=404, detail="group not found")
    return group


def _require_participant(session: Session, meetup_id: int, user: User) -> tuple[Meetup, MeetupParticipant]:
    meetup = meetup_service.get_meetup(session, meetup_id)
    if not meetup:
        raise HTTPException(status_code=404, detail="meetup not found")
    participant = meetup_service.get_participant(session, meetup_id, user.id)
    if not participant:
        raise HTTPException(status_code=403, detail="not a participant")
    return meetup, participant


# ------------------------------------------------------------------- me --

@router.get("/me")
def me(current_user: User = CurrentUser):
    return {
        "id": current_user.id,
        "display_name": current_user.display_name,
        "has_payment_method": bool(current_user.default_payment_method_id),
        "payout_ready": bool(current_user.stripe_account_id),
    }


@router.post("/card-setup")
def card_setup(current_user: User = CurrentUser, session: Session = Db):
    user = session.get(User, current_user.id)
    url = payments.create_card_setup_checkout_url(user, "/stripe/setup-return")
    session.add(user)
    session.commit()
    return {"url": url}


# --------------------------------------------------------------- groups --

class CreateGroupBody(BaseModel):
    name: str


class JoinGroupBody(BaseModel):
    invite_code: str


@router.get("/groups")
def list_groups(current_user: User = CurrentUser, session: Session = Db):
    user = session.get(User, current_user.id)
    groups = identity_service.user_groups(session, user)
    return [{"id": g.id, "name": g.name, "invite_code": g.invite_code} for g in groups]


@router.post("/groups")
def create_group(body: CreateGroupBody, current_user: User = CurrentUser, session: Session = Db):
    user = session.get(User, current_user.id)
    group = identity_service.create_app_group(session, user, body.name)
    return {"id": group.id, "name": group.name, "invite_code": group.invite_code}


@router.post("/groups/join")
def join_group(body: JoinGroupBody, current_user: User = CurrentUser, session: Session = Db):
    user = session.get(User, current_user.id)
    group = identity_service.get_group_by_invite_code(session, body.invite_code.strip())
    if not group:
        raise HTTPException(status_code=404, detail="invalid invite code")
    identity_service.ensure_membership(session, group, user)
    return {"id": group.id, "name": group.name, "invite_code": group.invite_code}


@router.get("/groups/{group_id}/members")
def group_members(group_id: int, current_user: User = CurrentUser, session: Session = Db):
    user = session.get(User, current_user.id)
    group = _require_membership(session, group_id, user)
    members = identity_service.group_members(session, group)
    return [{"id": m.id, "display_name": m.display_name} for m in members]


# -------------------------------------------------------------- meetups --

class CreateMeetupBody(BaseModel):
    member_ids: list[int]
    deposit_amount: int
    place_name: str
    scheduled_at: datetime


def _meetup_summary(meetup: Meetup) -> dict:
    return {
        "id": meetup.id,
        "place_name": meetup.place_name,
        "scheduled_at": meetup.scheduled_at.isoformat(),
        "status": meetup.status,
        "group_id": meetup.group_id,
    }


@router.get("/meetups")
def list_meetups(current_user: User = CurrentUser, session: Session = Db):
    user = session.get(User, current_user.id)
    from sqlmodel import select

    meetups = session.exec(
        select(Meetup)
        .join(MeetupParticipant, MeetupParticipant.meetup_id == Meetup.id)
        .where(MeetupParticipant.user_id == user.id)
        .order_by(Meetup.created_at.desc())
    ).all()
    return [_meetup_summary(m) for m in meetups]


@router.post("/groups/{group_id}/meetups")
def create_meetup(group_id: int, body: CreateMeetupBody, current_user: User = CurrentUser, session: Session = Db):
    user = session.get(User, current_user.id)
    group = _require_membership(session, group_id, user)

    member_ids = set(body.member_ids)
    member_ids.discard(user.id)
    members = identity_service.group_members(session, group)
    valid_ids = {m.id for m in members}
    if not member_ids or not member_ids.issubset(valid_ids):
        raise HTTPException(status_code=400, detail="invalid member selection")

    meetup = Meetup(
        group_id=group.id, creator_id=user.id, place_name=body.place_name.strip(),
        scheduled_at=body.scheduled_at, status=MeetupStatus.COLLECTING_DEPOSIT,
    )
    session.add(meetup)
    session.commit()
    session.refresh(meetup)

    for uid in member_ids | {user.id}:
        session.add(MeetupParticipant(meetup_id=meetup.id, user_id=uid, deposit_amount=body.deposit_amount))
    session.commit()

    scheduler.schedule_meetup_jobs(meetup.id, meetup.scheduled_at)

    participants = meetup_service.get_participants(session, meetup.id)
    deposit_service.request_all_deposits(session, meetup, participants)
    deposit_service.activate_if_ready(session, meetup, participants)

    for p in participants:
        member = session.get(User, p.user_id)
        line_client.push(member.line_user_id, [fx.arrival_button_flex(meetup.id, meetup.place_name)])
        line_client.push(member.line_user_id, [fx.location_share_prompt()])

    session.refresh(meetup)
    return _meetup_summary(meetup)


@router.get("/meetups/{meetup_id}")
def meetup_detail(meetup_id: int, current_user: User = CurrentUser, session: Session = Db):
    user = session.get(User, current_user.id)
    meetup, _ = _require_participant(session, meetup_id, user)
    participants = meetup_service.get_participants(session, meetup_id)

    rows = []
    for p in participants:
        member = session.get(User, p.user_id)
        rows.append({
            "user_id": p.user_id,
            "display_name": member.display_name,
            "deposit_amount": p.deposit_amount,
            "deposit_status": p.deposit_status,
            "arrived": p.arrived_at is not None,
            "is_late": p.is_late,
            "declared_minutes": p.declared_minutes,
            "declared_deadline_at": p.declared_deadline_at.isoformat() if p.declared_deadline_at else None,
            "penalty_amount": p.penalty_amount,
            "payout_amount": p.payout_amount if meetup.status == MeetupStatus.COMPLETED else None,
        })

    return {**_meetup_summary(meetup), "participants": rows}


@router.post("/meetups/{meetup_id}/arrive")
def arrive(meetup_id: int, current_user: User = CurrentUser, session: Session = Db):
    from app.services import penalty_service

    user = session.get(User, current_user.id)
    meetup, participant = _require_participant(session, meetup_id, user)
    if participant.arrived_at:
        return {"ok": True, "already": True}
    penalty_service.mark_arrived(session, meetup, participant)
    return {"ok": True}


class DeclareLateBody(BaseModel):
    minutes: int


@router.post("/meetups/{meetup_id}/declare-late")
def declare_late(meetup_id: int, body: DeclareLateBody, current_user: User = CurrentUser, session: Session = Db):
    from app.services import penalty_service

    if body.minutes <= 0 or body.minutes > 240:
        raise HTTPException(status_code=400, detail="minutes must be between 1 and 240")
    user = session.get(User, current_user.id)
    meetup, participant = _require_participant(session, meetup_id, user)
    if not participant.is_late:
        raise HTTPException(status_code=400, detail="not flagged late yet")
    penalty_service.declare_late(session, meetup, participant, body.minutes)
    return {"ok": True}


class LocationBody(BaseModel):
    latitude: float
    longitude: float


@router.post("/meetups/{meetup_id}/location")
def post_location(meetup_id: int, body: LocationBody, current_user: User = CurrentUser, session: Session = Db):
    user = session.get(User, current_user.id)
    _require_participant(session, meetup_id, user)
    location_service.record_location(session, meetup_id, user.id, body.latitude, body.longitude)
    return {"ok": True}


@router.get("/meetups/{meetup_id}/locations")
def get_locations(meetup_id: int, current_user: User = CurrentUser, session: Session = Db):
    user = session.get(User, current_user.id)
    _require_participant(session, meetup_id, user)
    now = datetime.utcnow()
    out = []
    for loc in location_service.latest_locations(session, meetup_id):
        member = session.get(User, loc.user_id)
        out.append({
            "user_id": loc.user_id,
            "display_name": member.display_name,
            "latitude": loc.latitude,
            "longitude": loc.longitude,
            "minutes_ago": max(0, int((now - loc.shared_at).total_seconds() // 60)),
        })
    return out


# ----------------------------------------------------------------- doubt --

@router.get("/meetups/{meetup_id}/doubts")
def get_doubts(meetup_id: int, current_user: User = CurrentUser, session: Session = Db):
    """Only ever reveals the caller's *own* predictions, never anyone else's."""
    user = session.get(User, current_user.id)
    meetup, _ = _require_participant(session, meetup_id, user)
    if meetup.status not in (MeetupStatus.DOUBT_PHASE, MeetupStatus.ACTIVE, MeetupStatus.SETTLING, MeetupStatus.COMPLETED):
        raise HTTPException(status_code=400, detail="doubt phase not open yet")

    participants = meetup_service.get_participants(session, meetup_id)
    from sqlmodel import select

    my_predictions = {
        pred.target_id: pred.predicted_late
        for pred in session.exec(
            select(DoubtPrediction).where(
                DoubtPrediction.meetup_id == meetup_id, DoubtPrediction.predictor_id == user.id
            )
        ).all()
    }

    out = []
    for p in participants:
        if p.user_id == user.id:
            continue
        member = session.get(User, p.user_id)
        out.append({
            "target_id": p.user_id,
            "display_name": member.display_name,
            "my_prediction": my_predictions.get(p.user_id),
        })
    return out


class DoubtBody(BaseModel):
    target_id: int
    predicted_late: bool


@router.post("/meetups/{meetup_id}/doubts")
def post_doubt(meetup_id: int, body: DoubtBody, current_user: User = CurrentUser, session: Session = Db):
    user = session.get(User, current_user.id)
    meetup, _ = _require_participant(session, meetup_id, user)
    if meetup.status != MeetupStatus.DOUBT_PHASE:
        raise HTTPException(status_code=400, detail="doubt phase is not open")
    target = meetup_service.get_participant(session, meetup_id, body.target_id)
    if not target or target.user_id == user.id:
        raise HTTPException(status_code=400, detail="invalid target")
    doubt_service.record_prediction(session, meetup_id, user.id, body.target_id, body.predicted_late)
    return {"ok": True}


@router.get("/meetups/{meetup_id}/settlement")
def settlement(meetup_id: int, current_user: User = CurrentUser, session: Session = Db):
    user = session.get(User, current_user.id)
    meetup, _ = _require_participant(session, meetup_id, user)
    if meetup.status != MeetupStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="not settled yet")
    participants = meetup_service.get_participants(session, meetup_id)
    out = []
    for p in participants:
        member = session.get(User, p.user_id)
        net = p.payout_amount - (0 if not p.is_late else p.deposit_amount + p.penalty_amount)
        out.append({
            "user_id": p.user_id,
            "display_name": member.display_name,
            "is_late": p.is_late,
            "payout_amount": p.payout_amount,
            "lost_amount": (p.deposit_amount + p.penalty_amount) if p.is_late else 0,
            "net": net,
        })
    return out
