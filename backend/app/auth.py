"""Shared-session auth — validate the tracker's `simmander_session` JWT.

Deck Doctor is served at simmander.app/deck-doctor, the same origin as the tracker,
so the browser sends the tracker's `simmander_session` cookie to /deck-doctor/api/*
automatically. We verify that JWT with the SHARED secret (HS256) to identify the
user — no tracker-DB access. `sub` is the integer user id; `admin` is a bool claim.
"""

from __future__ import annotations

import jwt
from fastapi import HTTPException, Request

from . import config

COOKIE_NAME = "simmander_session"


def _extract_token(request: Request) -> str | None:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        return token
    authz = request.headers.get("authorization", "")
    if authz.lower().startswith("bearer "):
        return authz[7:].strip() or None
    return None


def current_user(request: Request) -> dict | None:
    """{"id": int, "is_admin": bool} for a valid session, else None (anonymous)."""
    token = _extract_token(request)
    if not token:
        return None
    try:
        payload = jwt.decode(
            token, config.SIMMANDER_JWT_SECRET, algorithms=[config.SIMMANDER_JWT_ALG])
    except jwt.PyJWTError:
        return None
    sub = payload.get("sub")
    try:
        uid = int(sub)
    except (TypeError, ValueError):
        return None
    return {"id": uid, "is_admin": bool(payload.get("admin", False))}


def require_user(request: Request) -> dict:
    """Same as current_user but 401s when anonymous (for protected routes)."""
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="login required")
    return user
