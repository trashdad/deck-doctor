from __future__ import annotations

import hashlib
import io
import json
import logging
import urllib.error

import pytest

from card_update.http import FetchError, UrllibFetcher

UA = "DeckDoctor-CardUpdate/1.0 (+https://simmander.app/deck-doctor)"


class FakeResp(io.BytesIO):
    def __init__(self, body: bytes, status: int = 200, headers: dict | None = None):
        super().__init__(body)
        self.status = status
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def _http_error(url: str, code: int, headers: dict | None = None) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url, code, f"HTTP {code}", headers or {}, io.BytesIO(b""))


class Opener:
    """Scripted transport: each call pops the next outcome (bytes, exception or FakeResp)."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def __call__(self, req, timeout):
        self.requests.append((req, timeout))
        out = self.outcomes.pop(0)
        if isinstance(out, BaseException):
            raise out
        return out if isinstance(out, FakeResp) else FakeResp(out)


def _fetcher(opener, clock, retries=3):
    return UrllibFetcher(user_agent=UA, timeout_s=30, retries=retries, backoff_s=2,
                         backoff_max_s=10, min_interval_s=0.1, clock=clock,
                         log=logging.getLogger("t"), opener=opener)


def test_get_json_sends_generic_ua_and_accept(clock):
    op = Opener(json.dumps({"ok": 1}).encode())
    assert _fetcher(op, clock).get_json("https://api.scryfall.com/x") == {"ok": 1}
    req, timeout = op.requests[0]
    assert req.get_header("User-agent") == UA
    assert req.get_header("Accept") == "application/json"
    assert timeout == 30


def test_transient_errors_are_retried_with_backoff(clock):
    op = Opener(urllib.error.URLError("dns"), _http_error("u", 503), b'{"ok": 2}')
    assert _fetcher(op, clock).get_json("https://h/x") == {"ok": 2}
    assert len(op.requests) == 3
    assert [s for s in clock.sleeps if s >= 1] == [2, 4]


def test_client_errors_are_not_retried(clock):
    op = Opener(_http_error("u", 404))
    with pytest.raises(FetchError) as ei:
        _fetcher(op, clock).get_json("https://h/missing")
    assert "404" in str(ei.value)
    assert len(op.requests) == 1


def test_retries_are_bounded(clock):
    op = Opener(*[TimeoutError("slow")] * 4)
    with pytest.raises(FetchError) as ei:
        _fetcher(op, clock, retries=3).get_json("https://h/x")
    assert "4 attempt" in str(ei.value)
    assert len(op.requests) == 4


def test_429_honours_retry_after_within_cap(clock):
    op = Opener(_http_error("u", 429, {"Retry-After": "7"}), b"{}")
    _fetcher(op, clock).get_json("https://h/x")
    assert 7 in clock.sleeps


def test_requests_to_one_host_are_throttled(clock):
    op = Opener(b"{}", b"{}")
    f = _fetcher(op, clock)
    f.get_json("https://api.scryfall.com/a")
    f.get_json("https://api.scryfall.com/b")
    assert any(abs(s - 0.1) < 1e-9 for s in clock.sleeps)


def test_post_json_sends_body(clock):
    op = Opener(b'{"data": []}')
    _fetcher(op, clock).post_json("https://h/c", {"identifiers": [{"id": "x"}]})
    req, _ = op.requests[0]
    assert req.get_method() == "POST"
    assert json.loads(req.data) == {"identifiers": [{"id": "x"}]}
    assert req.get_header("Content-type") == "application/json"


def test_download_is_atomic_and_hashed(tmp_path, clock):
    body = b"x" * 5000
    op = Opener(FakeResp(body, headers={"Content-Length": "5000"}))
    dest = tmp_path / "f.gz"
    res = _fetcher(op, clock).download("https://h/f.gz", dest, expected_size=5000, min_size=10)
    assert dest.read_bytes() == body
    assert res.size == 5000 and res.sha256 == hashlib.sha256(body).hexdigest()
    assert not (tmp_path / "f.gz.part").exists()


def test_download_size_mismatch_retries_then_fails_and_leaves_nothing(tmp_path, clock):
    op = Opener(b"short", b"short", b"short", b"short")
    dest = tmp_path / "f.gz"
    with pytest.raises(FetchError) as ei:
        _fetcher(op, clock).download("https://h/f.gz", dest, expected_size=5000)
    assert "5,000" in str(ei.value) and "4 attempt" in str(ei.value)
    assert not dest.exists() and not (tmp_path / "f.gz.part").exists()


def test_download_over_max_size_aborts_without_retry(tmp_path, clock):
    op = Opener(b"y" * 3000)
    dest = tmp_path / "f"
    with pytest.raises(FetchError) as ei:
        _fetcher(op, clock).download("https://h/f", dest, max_size=1000)
    assert "max" in str(ei.value)
    assert len(op.requests) == 1
    assert not dest.exists() and not (tmp_path / "f.part").exists()


def test_download_under_min_size_fails(tmp_path, clock):
    op = Opener(b"tiny")
    with pytest.raises(FetchError) as ei:
        _fetcher(op, clock).download("https://h/f", tmp_path / "f", min_size=100)
    assert "min" in str(ei.value)


def test_download_with_expected_sha_mismatch_fails(tmp_path, clock):
    op = Opener(b"abc", b"abc", b"abc", b"abc")
    with pytest.raises(FetchError):
        _fetcher(op, clock).download("https://h/f", tmp_path / "f", expected_sha256="0" * 64)
    assert not (tmp_path / "f").exists()


def test_get_text_caps_size(clock):
    op = Opener(b"MIT License\n" + b"z" * 50)
    assert _fetcher(op, clock).get_text("https://h/LICENSE", max_bytes=1000).startswith("MIT License")
    op2 = Opener(b"z" * 2000)
    with pytest.raises(FetchError):
        _fetcher(op2, clock).get_text("https://h/LICENSE", max_bytes=1000)
