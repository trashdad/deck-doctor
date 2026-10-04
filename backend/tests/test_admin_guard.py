"""Admin endpoints must not be reachable from the public internet.

nginx proxies simmander.app/deck-doctor/api/* to 127.0.0.1:8002 and always sets
X-Real-IP / X-Forwarded-For. The nightly refresh (deploy/refresh_corpus.sh) calls
http://localhost:8002/admin/reload directly, with neither header. So: loopback
callers WITHOUT proxy headers are trusted; everyone else needs an admin session.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jwt  # noqa: E402
import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from starlette.requests import Request  # noqa: E402

from app import auth, config  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


def _token(user_id: int, *, admin: bool = False) -> str:
    return jwt.encode(
        {"sub": str(user_id), "admin": admin, "exp": int(time.time()) + 3600},
        config.SIMMANDER_JWT_SECRET, algorithm=config.SIMMANDER_JWT_ALG)


def _req(host: str, headers: list[tuple[str, str]] = ()) -> Request:
    return Request({
        "type": "http",
        "client": (host, 50000),
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers],
    })


def _assert_forbidden(request: Request) -> None:
    with pytest.raises(HTTPException) as exc:
        auth.require_local_or_admin(request)
    assert exc.value.status_code == 403


def test_loopback_without_proxy_headers_is_allowed():
    auth.require_local_or_admin(_req("127.0.0.1"))


def test_ipv6_loopback_without_proxy_headers_is_allowed():
    auth.require_local_or_admin(_req("::1"))


def test_proxied_request_is_rejected_even_though_nginx_connects_from_loopback():
    _assert_forbidden(_req("127.0.0.1", [("X-Real-IP", "203.0.113.9")]))


def test_forwarded_for_header_alone_marks_request_as_proxied():
    _assert_forbidden(_req("127.0.0.1", [("X-Forwarded-For", "203.0.113.9")]))


def test_non_loopback_client_is_rejected():
    _assert_forbidden(_req("203.0.113.9"))


def test_admin_session_is_allowed_through_the_proxy():
    auth.require_local_or_admin(_req("127.0.0.1", [
        ("X-Real-IP", "203.0.113.9"),
        ("Authorization", f"Bearer {_token(1, admin=True)}"),
    ]))


def test_non_admin_session_is_rejected():
    _assert_forbidden(_req("127.0.0.1", [
        ("X-Real-IP", "203.0.113.9"),
        ("Authorization", f"Bearer {_token(42, admin=False)}"),
    ]))


def test_reload_endpoint_rejects_anonymous_public_request():
    r = client.post("/admin/reload",
                    headers={"X-Real-IP": "203.0.113.9", "X-Forwarded-For": "203.0.113.9"})
    assert r.status_code == 403
