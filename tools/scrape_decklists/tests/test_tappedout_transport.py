"""TappedOut transport (2026-11-25): the nodriver browser transport and the
1-request-per-30-seconds courtesy cap. No network, no Chrome, here."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRAPER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRAPER))

import runner  # noqa: E402


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """Never start Chrome or touch the network in this file."""
    monkeypatch.setattr(runner, "_ensure_tappedout_browser", lambda: None)
    monkeypatch.setattr(runner, "_host_last", {"tappedout.net": 0.0})
    monkeypatch.setattr(runner.time, "sleep", lambda s: None)


def test_tappedout_interval_is_at_least_30s():
    assert runner._HOST_INTERVAL["tappedout.net"] >= 30.0


def test_tappedout_grant_caps_interval_at_30s():
    g = runner._grant_for("tappedout.net")
    assert g is not None
    assert float(g["min_interval_s"]) >= 30.0


def test_tappedout_throttle_enforces_30s(monkeypatch):
    slept = []
    clock = {"t": 100.0}

    def _fake_sleep(s):
        slept.append(s)
        clock["t"] += s

    monkeypatch.setattr(runner.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(runner.time, "sleep", _fake_sleep)
    monkeypatch.setattr(runner, "_host_last", {"tappedout.net": 100.0})
    monkeypatch.setattr(runner, "_GRANTS", {})
    runner._throttle("tappedout.net", "/mtg-decks/search/")
    assert slept == [30.0]


def test_tappedout_get_uses_browser_transport(monkeypatch):
    fake_html = "<html><div class='board-container'></div></html>"
    monkeypatch.setattr(runner, "_to_failed", False)
    monkeypatch.setattr(runner, "_tappedout_browser_html",
                        lambda url, marker, timeout=60: fake_html)
    r = runner._tappedout_get("https://tappedout.net/mtg-decks/x/", "board-container")
    assert r.status_code == 200
    assert r.text == fake_html


def test_tappedout_get_falls_back_when_browser_unavailable(monkeypatch):
    monkeypatch.setattr(runner, "_to_failed", True)
    calls = []

    class _Resp:
        status_code = 200
        text = "<html>real page</html>"

    class _Sess:
        def get(self, url, timeout=30):
            calls.append(url)
            return _Resp()

    monkeypatch.setattr(runner, "_cloudscraper", lambda: _Sess())
    r = runner._tappedout_get("https://tappedout.net/mtg-decks/x/", "board-container")
    assert r.status_code == 200 and r.text == "<html>real page</html>"
    assert calls == ["https://tappedout.net/mtg-decks/x/"]


def test_fallback_applies_throttle_exactly_once(monkeypatch):
    """The fallback must not double-throttle (it bypasses _cs_get's own throttle)."""
    monkeypatch.setattr(runner, "_to_failed", True)
    throttled = []
    monkeypatch.setattr(runner, "_throttle", lambda host, path=None: throttled.append(host))

    class _Resp:
        status_code = 200
        text = "ok"

    class _Sess:
        def get(self, url, timeout=30):
            return _Resp()

    monkeypatch.setattr(runner, "_cloudscraper", lambda: _Sess())
    runner._tappedout_get("https://tappedout.net/mtg-decks/x/", "board-container")
    assert throttled == ["tappedout.net"]


def test_fallback_detects_cloudflare_challenge(capsys, monkeypatch):
    monkeypatch.setattr(runner, "_to_failed", True)

    class _Resp:
        status_code = 403
        text = "<html><title>Just a moment...</title></html>"

    class _Sess:
        def get(self, url, timeout=30):
            return _Resp()

    monkeypatch.setattr(runner, "_cloudscraper", lambda: _Sess())
    r = runner._tappedout_get("https://tappedout.net/mtg-decks/x/", "board-container")
    assert r.status_code == 403
    assert "Cloudflare" in capsys.readouterr().err


def test_browser_failure_propagates_when_transport_up(monkeypatch):
    monkeypatch.setattr(runner, "_to_failed", False)

    def _boom(url, marker, timeout=60):
        raise TimeoutError("challenge not cleared")

    monkeypatch.setattr(runner, "_tappedout_browser_html", _boom)
    with pytest.raises(TimeoutError):
        runner._tappedout_get("https://tappedout.net/mtg-decks/x/", "board-container")


def test_tappedout_fetchers_route_through_browser_transport(monkeypatch):
    captured = []

    def _fake_get(url, marker, timeout=60):
        captured.append((url, marker))
        return runner._TappedOutResponse("<html></html>")

    monkeypatch.setattr(runner, "_tappedout_get", _fake_get)
    runner._fetch_tappedout("some-slug")
    runner._tappedout_recent_page(1)
    assert ("https://tappedout.net/mtg-decks/some-slug/", "board-container") in captured
    assert ("https://tappedout.net/mtg-decks/search/?q=&format=edh&order=-date_updated&p=1",
            "/mtg-decks/") in captured
