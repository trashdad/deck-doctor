"""reseed: re-collect real decklists per commander after the 2026-10 shell bug."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRAPER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRAPER))

import reseed  # noqa: E402
import runner  # noqa: E402


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "CORPUS_DIR", tmp_path / "decklists")
    monkeypatch.setattr(runner, "SEEN_FILE", tmp_path / "decklists" / ".seen_deck_ids")
    (tmp_path / "decklists").mkdir()
    (tmp_path / "decklists" / ".seen_deck_ids").write_text("moxfield:old\n", encoding="utf-8")
    return runner.Corpus(batch="reseed")


def _previews(mapping):
    """urlhash -> (source, native_id) ; anything else raises like a failed fetch."""
    def fetch(h):
        if h not in mapping:
            raise RuntimeError(f"HTTP 404 for {h}")
        source, nid = mapping[h]
        if source is None:
            return None  # deckpreview whose URL is not a known source
        return source, nid, "Krenko, Mob Boss", ["Krenko, Mob Boss", f"Card {nid}"]
    return fetch


def test_stops_after_target_new_decks(corpus):
    hashes = ["h1", "h2", "h3", "h4", "h5", "h6"]
    mapping = {"h1": ("moxfield", "old"), "h2": ("moxfield", "a"), "h4": ("moxfield", "b"),
               "h5": (None, None), "h6": ("moxfield", "c")}
    res = reseed.reseed_commander(
        corpus, "Krenko, Mob Boss", target=2, max_rows=10,
        hashes_fn=lambda c, limit: hashes[:limit], preview_fn=_previews(mapping), workers=1)
    # h1 already seen, h2 new, h3 fails, h4 new -> target reached; h5/h6 never read.
    assert res == {"commander": "Krenko, Mob Boss", "target": 2, "added": 2,
                   "counted": 2, "scanned": 4, "failed": 1}
    lines = (runner.CORPUS_DIR / "moxfield-reseed.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(x)["deck_id"] for x in lines] == ["moxfield:a", "moxfield:b"]


def test_uncounted_ids_are_written_but_do_not_count(corpus):
    hashes = ["h1", "h2", "h3"]
    mapping = {"h1": ("archidekt", "9"), "h2": ("moxfield", "a"), "h3": ("moxfield", "b")}
    res = reseed.reseed_commander(
        corpus, "Krenko, Mob Boss", target=2, max_rows=10,
        hashes_fn=lambda c, limit: hashes[:limit], preview_fn=_previews(mapping),
        uncounted={"archidekt:9"}, workers=1)
    assert res["added"] == 3
    assert res["counted"] == 2
    assert res["scanned"] == 3


def test_max_rows_caps_the_walk(corpus):
    hashes = [f"h{i}" for i in range(50)]
    mapping = {h: ("moxfield", "old") for h in hashes}  # every row already seen
    res = reseed.reseed_commander(
        corpus, "Krenko, Mob Boss", target=5, max_rows=7,
        hashes_fn=lambda c, limit: hashes[:limit], preview_fn=_previews(mapping), workers=3)
    assert res["scanned"] == 7
    assert res["added"] == 0


def test_listing_failure_is_reported_not_raised(corpus):
    def boom(c, limit):
        raise RuntimeError("HTTP 404 listing")
    res = reseed.reseed_commander(
        corpus, "No Such Commander", target=3, max_rows=10,
        hashes_fn=boom, preview_fn=_previews({}), workers=1)
    assert res["scanned"] == 0 and res["added"] == 0
    assert res["error"].startswith("listing:")


def test_read_targets(tmp_path):
    p = tmp_path / "t.tsv"
    p.write_text("Krenko, Mob Boss\t186\nAtraxa, Praetors' Voice\t0\n\n", encoding="utf-8")
    assert reseed.read_targets(p) == [("Krenko, Mob Boss", 186)]


def test_decks_already_fetched_in_the_last_chunk_are_kept(corpus):
    # target is met on the first row of a 3-row chunk; the other two rows were
    # already fetched, so they are written instead of thrown away.
    hashes = ["h1", "h2", "h3", "h4"]
    mapping = {h: ("moxfield", h) for h in hashes}
    res = reseed.reseed_commander(
        corpus, "Krenko, Mob Boss", target=1, max_rows=10,
        hashes_fn=lambda c, limit: hashes[:limit], preview_fn=_previews(mapping), workers=3)
    assert res["added"] == 3
    assert res["scanned"] == 3
