from sqlmodel import Session, select

from app.models import Group, GroupMember, User


def get_or_create_user(session: Session, line_user_id: str, display_name: str = "") -> User:
    user = session.exec(select(User).where(User.line_user_id == line_user_id)).first()
    if user:
        if display_name and user.display_name != display_name:
            user.display_name = display_name
            session.add(user)
            session.commit()
            session.refresh(user)
        return user
    user = User(line_user_id=line_user_id, display_name=display_name)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def get_or_create_group(session: Session, line_group_id: str) -> Group:
    group = session.exec(select(Group).where(Group.line_group_id == line_group_id)).first()
    if group:
        return group
    group = Group(line_group_id=line_group_id)
    session.add(group)
    session.commit()
    session.refresh(group)
    return group


def ensure_membership(session: Session, group: Group, user: User) -> None:
    existing = session.exec(
        select(GroupMember).where(GroupMember.group_id == group.id, GroupMember.user_id == user.id)
    ).first()
    if existing:
        return
    session.add(GroupMember(group_id=group.id, user_id=user.id))
    session.commit()


def group_members(session: Session, group: Group) -> list[User]:
    rows = session.exec(
        select(User).join(GroupMember, GroupMember.user_id == User.id).where(GroupMember.group_id == group.id)
    ).all()
    return rows
