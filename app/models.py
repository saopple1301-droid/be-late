"""Database models.

Money amounts are stored as integers in the smallest *counting* unit of the
configured currency (yen has no subunit, so ¥500 == 500). Adjust if you
switch CURRENCY to a currency with decimal subunits.
"""
from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.utcnow()


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    line_user_id: str = Field(index=True, unique=True)
    display_name: str = ""

    stripe_customer_id: Optional[str] = None
    default_payment_method_id: Optional[str] = None
    # Stripe Connect account used to receive payouts of forfeited deposits.
    # Optional: a user can participate and pay without ever setting this up,
    # they just won't be able to receive automatic payouts (see payments.py).
    stripe_account_id: Optional[str] = None

    created_at: datetime = Field(default_factory=utcnow)


class Group(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    line_group_id: str = Field(index=True, unique=True)
    name: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class GroupMember(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    group_id: int = Field(foreign_key="group.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    joined_at: datetime = Field(default_factory=utcnow)


class MeetupStatus:
    DRAFT = "draft"                 # wizard in progress, not yet visible to others
    COLLECTING_DEPOSIT = "collecting_deposit"  # deposits being authorized
    DOUBT_PHASE = "doubt_phase"     # T-2h prediction window open
    ACTIVE = "active"               # meetup time reached, tracking arrivals
    SETTLING = "settling"           # arrivals done, computing/charging penalties
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Meetup(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    group_id: int = Field(foreign_key="group.id", index=True)
    creator_id: int = Field(foreign_key="user.id")
    place_name: str = ""
    scheduled_at: datetime
    status: str = MeetupStatus.DRAFT
    doubt_job_fired: bool = False
    deadline_job_fired: bool = False
    settled_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow)


class DepositStatus:
    PENDING = "pending"          # created, waiting on user to authorize payment
    AUTHORIZED = "authorized"    # held (manual-capture PaymentIntent succeeded)
    CAPTURED = "captured"        # forfeited to the group, captured on Stripe
    RELEASED = "released"        # returned to the user (arrived on time)
    FAILED = "failed"


class MeetupParticipant(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    meetup_id: int = Field(foreign_key="meetup.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)

    deposit_amount: int = 0
    deposit_intent_id: Optional[str] = None
    deposit_status: str = DepositStatus.PENDING

    arrived_at: Optional[datetime] = None
    is_late: bool = False

    # Set once, after the scheduled time passes and the user hasn't arrived:
    # "何分以内に到着するか" (minutes from now they promise to arrive within).
    declared_minutes: Optional[int] = None
    declared_deadline_at: Optional[datetime] = None
    declared_deadline_job_fired: bool = False

    # Additional penalty charged if the declared deadline is also missed.
    penalty_amount: int = 0
    penalty_intent_id: Optional[str] = None
    penalty_status: str = "none"  # none, charged, failed

    # Share of other members' forfeited deposits/penalties owed to this user.
    payout_amount: int = 0
    payout_status: str = "pending"  # pending, transferred, manual_required

    created_at: datetime = Field(default_factory=utcnow)


class LocationShare(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    meetup_id: int = Field(foreign_key="meetup.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    latitude: float
    longitude: float
    shared_at: datetime = Field(default_factory=utcnow)


class DoubtPrediction(SQLModel, table=True):
    """predictor_id's private guess about whether target_id will be late.

    Never surfaced to target_id or to other group members - only used to
    compute rewards after the meetup settles. This is what keeps the
    "who doubted whom" information hidden (the スキル spec's トランプの
    ダウト-like rule).
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    meetup_id: int = Field(foreign_key="meetup.id", index=True)
    predictor_id: int = Field(foreign_key="user.id", index=True)
    target_id: int = Field(foreign_key="user.id", index=True)
    predicted_late: bool

    correct: Optional[bool] = None
    reward_amount: int = 0

    created_at: datetime = Field(default_factory=utcnow)


class DraftStep:
    SELECT_MEMBERS = "select_members"
    SELECT_DEPOSIT = "select_deposit"
    SELECT_PLACE = "select_place"
    SELECT_TIME = "select_time"
    CONFIRM = "confirm"


class MeetupDraft(SQLModel, table=True):
    """In-progress "collect friends -> deposit -> time" wizard state.

    One draft per (group, creator) at a time; started via the "集合" command
    and torn down once the meetup is confirmed or cancelled.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    group_id: int = Field(foreign_key="group.id", index=True)
    creator_id: int = Field(foreign_key="user.id", index=True)
    step: str = DraftStep.SELECT_MEMBERS
    selected_member_ids_json: str = "[]"
    deposit_amount: Optional[int] = None
    place_name: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=utcnow)
