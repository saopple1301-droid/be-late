"""Verifies the LIFF ID token the companion PWA sends on every API call.

The web app never sees the LINE channel secret - it only gets a short-lived
ID token from `liff.getIDToken()` after the user logs in through LINE. We
verify that token server-side on each request (LINE's `/oauth2/v2.1/verify`
endpoint), which also gives us the authoritative `sub` (LINE user id) and
profile fields, so there's no separate password/session system to build or
leak.
"""
from __future__ import annotations

import time

import httpx
from fastapi import Header, HTTPException
from sqlmodel import Session

from app.config import settings
from app.database import get_session
from app.models import User
from app.services import identity_service

_VERIFY_URL = "https://api.line.me/oauth2/v2.1/verify"

_cache: dict[str, tuple[float, dict]] = {}
_CACHE_TTL_SECONDS = 60


def _verify_id_token(id_token: str) -> dict:
    cached = _cache.get(id_token)
    if cached and cached[0] > time.time():
        return cached[1]

    resp = httpx.post(_VERIFY_URL, data={"id_token": id_token, "client_id": settings.liff_channel_id})
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="invalid LIFF id token")
    payload = resp.json()
    _cache[id_token] = (time.time() + _CACHE_TTL_SECONDS, payload)
    return payload


def get_current_user(authorization: str = Header(default="")) -> User:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    id_token = authorization.removeprefix("Bearer ").strip()

    payload = _verify_id_token(id_token)
    line_user_id = payload.get("sub")
    if not line_user_id:
        raise HTTPException(status_code=401, detail="token missing subject")

    with get_session() as session:
        user = identity_service.get_or_create_user(session, line_user_id, payload.get("name", ""))
        session.expunge(user)
        return user


def db() -> Session:
    with get_session() as session:
        yield session
