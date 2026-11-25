"""Compliance block (2026-11-24): the scraper must not reach EDHREC, Archidekt or
Moxfield. See docs/plans/2026-11-24-edhrec-compliance.md."""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

import pytest

SCRAPER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRAPER))

import runner  # noqa: E402


@pytest.fixture(autouse=True)
def no_grants(monkeypatch):
    """The block tests run with NO grants, whatever permissions.json ships."""
    monkeypatch.setattr(runner, "_GRANTS", {})


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Any real request fails the test loudly instead of hitting a site."""
    def _boom(*_a, **_k):
        raise AssertionError("network request attempted")
    monkeypatch.setattr(urllib.request, "urlopen", _boom)


@pytest.mark.parametrize("url", [
    "https://json.edhrec.com/pages/commanders/krenko-mob-boss.json",
    "https://edhrec.com/api/deckpreview/abc",
    "https://EDHREC.com/anything",
    "https://archidekt.com/api/decks/1/",
    "https://www.archidekt.com/api/decks/1/",
    "https://api2.moxfield.com/v3/decks/all/x",
    "https://moxfield.com/decks/x",
])
def test_disabled_hosts_refused_before_any_request(url):
    with pytest.raises(runner.SourceDisabled):
        runner._get_json(url)


def test_fetchers_for_disabled_sites_refuse():
    with pytest.raises(runner.SourceDisabled):
        runner._fetch_edhrec("Krenko, Mob Boss")
    with pytest.raises(runner.SourceDisabled):
        runner._fetch_edhrec_deckpreview("abc")
    with pytest.raises(runner.SourceDisabled):
        runner._edhrec_deck_hashes("Krenko, Mob Boss")
    with pytest.raises(runner.SourceDisabled):
        runner._fetch_archidekt("1")
    with pytest.raises(runner.SourceDisabled):
        runner._fetch_moxfield("x")
    with pytest.raises(runner.SourceDisabled):
        runner._archidekt_recent_page(1)


def test_lookalike_hosts_not_blocked():
    assert not runner._host_disabled("notedhrec.com")
    assert not runner._host_disabled("tappedout.net")
    assert runner._host_disabled("json.edhrec.com")


@pytest.mark.parametrize("argv", [
    ["edhrec", "--id", "Krenko, Mob Boss"],
    ["archidekt", "--id", "1"],
    ["moxfield", "--id", "x"],
    ["seeds", "--top", "5"],
    ["recent", "--recent-source", "archidekt"],
])
def test_cli_refuses_disabled_sources_without_writing(argv, tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "CORPUS_DIR", tmp_path / "decklists")
    monkeypatch.setattr(runner, "SEEN_FILE", tmp_path / "decklists" / ".seen_deck_ids")
    assert runner.main(argv) == 2
    assert not (tmp_path / "decklists").exists()


def test_recent_requires_explicit_source():
    with pytest.raises(SystemExit):
        runner.main(["recent"])


# ── permissions.json grants ───────────────────────────────────────────────────
import json  # noqa: E402

GOOD = {"host": "edhrec.com", "granted_by": "EDHREC staff", "date": "2026-12-01",
        "evidence": "docs/permissions/edhrec.md"}


def _grants(tmp_path, monkeypatch, *grants):
    f = tmp_path / "permissions.json"
    f.write_text(json.dumps({"grants": list(grants)}), encoding="utf-8")
    monkeypatch.setattr(runner, "_GRANTS", runner._load_grants(f))


def test_shipped_permissions_file_is_well_formed():
    raw = json.loads(runner._PERMISSIONS_FILE.read_text(encoding="utf-8"))["grants"]
    loaded = runner._load_grants()
    assert len(loaded) == len(raw), "a shipped grant is missing a required field"
    for g in loaded.values():
        assert float(g.get("min_interval_s", 1)) > 0
        assert "<" not in json.dumps(g) and ">" not in json.dumps(g), "placeholder left in grant"


def test_missing_or_corrupt_file_fails_closed(tmp_path):
    assert runner._load_grants(tmp_path / "nope.json") == {}
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert runner._load_grants(bad) == {}


@pytest.mark.parametrize("missing", ["host", "granted_by", "date", "evidence"])
def test_incomplete_grant_ignored(tmp_path, monkeypatch, missing):
    g = {k: v for k, v in GOOD.items() if k != missing}
    _grants(tmp_path, monkeypatch, g)
    assert runner._host_disabled("edhrec.com")


def test_grant_enables_host_and_source_only_for_that_host(tmp_path, monkeypatch):
    _grants(tmp_path, monkeypatch, GOOD)
    assert not runner._host_disabled("json.edhrec.com")
    assert not runner._source_disabled("edhrec") and not runner._source_disabled("seeds")
    assert runner._host_disabled("archidekt.com") and runner._source_disabled("archidekt")


def test_path_scope_enforced(tmp_path, monkeypatch):
    _grants(tmp_path, monkeypatch, {**GOOD, "allowed_path_prefixes": ["/pages/"]})
    runner._throttle("json.edhrec.com", "/pages/commanders/x.json")
    with pytest.raises(runner.SourceDisabled):
        runner._throttle("edhrec.com", "/api/deckpreview/abc")


def test_min_interval_slows_requests(tmp_path, monkeypatch):
    _grants(tmp_path, monkeypatch, {**GOOD, "min_interval_s": 7})
    slept = []
    monkeypatch.setattr(runner.time, "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(runner, "_host_last", {"edhrec.com": runner.time.monotonic()})
    runner._throttle("edhrec.com", "/x")
    runner._throttle("edhrec.com", "/x")
    assert slept and max(slept) > 3


def test_blanket_floor_six_seconds_for_every_host(monkeypatch):
    """No host (even ones with a faster per-host default) is hit more than once per 6 s."""
    slept = []
    monkeypatch.setattr(runner.time, "sleep", lambda s: slept.append(s))
    for host in ("json.edhrec.com", "api2.moxfield.com", "tappedout.net", "aetherhub.com",
                 "somewhere-new.example"):
        slept.clear()
        monkeypatch.setattr(runner, "_host_last", {host: runner.time.monotonic()})
        monkeypatch.setattr(runner, "_GRANTS", {})
        try:
            runner._throttle(host, "/x")
        except runner.SourceDisabled:
            continue  # blocked hosts never reach the sleep
        assert slept and max(slept) > 5.0, host
    assert runner.MIN_REQUEST_INTERVAL_S == 6.0
