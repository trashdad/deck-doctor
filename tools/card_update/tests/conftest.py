"""Shared fixtures. Every test runs with the network blocked (autouse)."""

from __future__ import annotations

import socket
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[2]
REPO = TOOLS.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Any real request fails the test loudly instead of reaching a site."""
    def _boom(*_a, **_k):
        raise AssertionError("network request attempted in a unit test")
    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    monkeypatch.setattr(socket.socket, "connect", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom)


class FakeClock:
    """Deterministic clock: sleep() advances time instead of waiting."""

    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or datetime(2026, 11, 26, 2, 30, tzinfo=timezone.utc)
        self._mono = 1000.0
        self.sleeps: list[float] = []

    def now(self) -> datetime:
        return self._now

    def monotonic(self) -> float:
        return self._mono

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.advance(seconds)

    def advance(self, seconds: float) -> None:
        self._mono += seconds
        self._now += timedelta(seconds=seconds)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


# ── offline end-to-end harness (see harness.py) ─────────────────────────────

@pytest.fixture(scope="session")
def baseline(tmp_path_factory) -> Path:
    """The live release before the update, built once with the real scoring scripts."""
    import harness
    d = tmp_path_factory.mktemp("baseline")
    harness.build_baseline(d)
    return d


@pytest.fixture(scope="session")
def gz() -> bytes:
    import harness
    return harness.gz_bytes()


@pytest.fixture
def h(tmp_path, baseline, gz, clock):
    import json

    import harness
    hh = harness.Harness(root=tmp_path, baseline=baseline, gz=gz, clock=clock)
    hh.state_file.parent.mkdir(parents=True, exist_ok=True)
    hh.state_file.write_text(json.dumps({"mtgish_sha": harness.OLD_SHA,
                                         "scryfall_updated_at": "2026-11-20T10:00:00.000+00:00",
                                         "current_release_id": "seed-1"}), encoding="utf-8")
    return hh
