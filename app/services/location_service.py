from datetime import datetime

from sqlmodel import Session, select

from app.models import LocationShare, MeetupParticipant, User


def record_location(session: Session, meetup_id: int, user_id: int, lat: float, lng: float) -> None:
    session.add(LocationShare(meetup_id=meetup_id, user_id=user_id, latitude=lat, longitude=lng))
    session.commit()


def latest_locations(session: Session, meetup_id: int) -> list[LocationShare]:
    participants = session.exec(
        select(MeetupParticipant).where(MeetupParticipant.meetup_id == meetup_id)
    ).all()
    out = []
    for p in participants:
        row = session.exec(
            select(LocationShare)
            .where(LocationShare.meetup_id == meetup_id, LocationShare.user_id == p.user_id)
            .order_by(LocationShare.shared_at.desc())
        ).first()
        if row:
            out.append(row)
    return out


def build_summary_lines(session: Session, meetup_id: int) -> list[str]:
    lines = []
    now = datetime.utcnow()
    for loc in latest_locations(session, meetup_id):
        user = session.get(User, loc.user_id)
        minutes_ago = max(0, int((now - loc.shared_at).total_seconds() // 60))
        maps_url = f"https://www.google.com/maps?q={loc.latitude},{loc.longitude}"
        lines.append(f"{user.display_name}（{minutes_ago}分前）\n{maps_url}")
    return lines
