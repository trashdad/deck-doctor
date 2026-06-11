"""Shared-session JWT validation tests."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jwt  # noqa: E402
import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from starlette.requests import Request  # noqa: E402

from app import auth, config  # noqa: E402


def _req(cookie: str | None = None, bearer: str | None = None) -> Request:
    headers = []
    if cookie is not None:
        headers.append((b"cookie", f"{auth.COOKIE_NAME}={cookie}".encode()))
    if bearer is not None:
        headers.append((b"authorization", f"Bearer {bearer}".encode()))
    return Request({"type": "http", "headers": headers})


def _token(user_id: int, *, admin: bool = False, exp_delta: int = 3600,
           secret: str | None = None) -> str:
    return jwt.encode(
        {"sub": str(user_id), "admin": admin, "exp": int(time.time()) + exp_delta},
        secret or config.SIMMANDER_JWT_SECRET, algorithm=config.SIMMANDER_JWT_ALG)


def test_valid_cookie_returns_user():
    u = auth.current_user(_req(cookie=_token(42, admin=True)))
    assert u == {"id": 42, "is_admin": True}


def test_valid_bearer_header_returns_user():
    assert auth.current_user(_req(bearer=_token(7)))["id"] == 7


def test_missing_cookie_returns_none():
    assert auth.current_user(_req()) is None


def test_expired_token_returns_none():
    assert auth.current_user(_req(cookie=_token(1, exp_delta=-10))) is None


def test_wrong_secret_returns_none():
    assert auth.current_user(_req(cookie=_token(1, secret="not-the-secret"))) is None


def test_require_user_raises_401_when_anonymous():
    with pytest.raises(HTTPException) as e:
        auth.require_user(_req())
    assert e.value.status_code == 401


def test_require_user_returns_user_when_valid():
    assert auth.require_user(_req(cookie=_token(9)))["id"] == 9
