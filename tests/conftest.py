import os

os.environ.setdefault("LINE_CHANNEL_SECRET", "test")
os.environ.setdefault("LINE_CHANNEL_ACCESS_TOKEN", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from sqlmodel import Session, SQLModel, create_engine

import app.database as database


@pytest.fixture()
def session(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)
    with Session(engine) as s:
        yield s


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Every test runs with LINE pushes/replies stubbed out (payments.py is
    already a no-op simulation - see app/payments.py - so it needs no
    stubbing)."""
    from app import line_client

    sent = []
    monkeypatch.setattr(line_client, "push", lambda to, messages: sent.append(("push", to, messages)))
    monkeypatch.setattr(line_client, "reply", lambda token, messages: sent.append(("reply", token, messages)))
    yield sent
