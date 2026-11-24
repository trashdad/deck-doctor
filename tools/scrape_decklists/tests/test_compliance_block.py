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
