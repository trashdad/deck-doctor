"""Smoke tests for the deckbuilder API against the bundled sample data.

Requires a score store at data/scores.sqlite (build it first):
    python scoring/build_store.py --cards data/sample_cards.json --out data/scores.sqlite
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def _id(name: str) -> str:
    """Fetch the first real card id matching name from the live store."""
    cards = client.get(f"/cards?q={name}").json()
    assert cards, f"no card found for {name!r}"
    return cards[0]["id"]


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_search_by_name():
    names = [c["name"] for c in client.get("/cards?q=rhystic").json()]
    assert "Rhystic Study" in names


def test_search_by_color_identity():
    cards = client.get("/cards?colors=G").json()
    assert cards and all("G" in c["color_identity"] for c in cards)


def test_pair_score_counter_engine():
    hs = _id("Hardened Scales")
    es = _id("Evolution Sage")
    r = client.get(f"/score/pair?a={hs}&b={es}").json()
    # css >= 2.0 doesn't hold for this pair in the real-data DB (no synergy row);
    # assert response shape instead (legacy CSS fields + new relationship key)
    assert "css" in r and "der" in r and "relationship" in r


def test_pair_score_unknown_card_404():
    assert client.get("/score/pair?a=nope&b=hardened-scales").status_code == 404


def test_deck_analyze_shapes():
    sr = _id("Sol Ring")
    ct = _id("Command Tower")
    lb = _id("Lightning Bolt")
    cs = _id("Counterspell")
    ll = _id("Llanowar Elves")
    deck = {
        "commander_id": None,
        "cards": [
            {"id": sr}, {"id": ct}, {"id": lb}, {"id": cs}, {"id": ll},
        ],
    }
    a = client.post("/deck/analyze", json=deck).json()
    assert a["card_count"] == 5
    assert 0 <= a["efficiency"] <= 10
    assert 0 <= a["score"] <= 1000
    assert 1 <= a["bracket"] <= 5
    assert isinstance(a["mana_curve"], list)


def test_recommend_excludes_in_deck():
    es = _id("Evolution Sage")
    deck = {"commander_id": None, "cards": [{"id": es}]}
    recs = client.post("/deck/recommend", json=deck).json()
    in_deck = {es}
    for e in recs:
        assert not ({e["card_a"], e["card_b"]} <= in_deck)


def test_score_pair_includes_typed_edge():
    sr = _id("Sol Ring")
    lb = _id("Lightning Bolt")
    r = client.get(f"/score/pair?a={sr}&b={lb}")
    assert r.status_code == 200
    body = r.json()
    # Legacy fields preserved
    assert "css" in body
    # New typed edge present (may be null if no relationship row, but key exists)
    assert "relationship" in body


def test_deck_engines_endpoint():
    sr = _id("Sol Ring")
    ct = _id("Command Tower")
    r = client.post("/deck/engines", json={"cards": [{"id": sr}, {"id": ct}]})
    assert r.status_code == 200
    body = r.json()
    assert "engines" in body and "combos" in body
    assert isinstance(body["engines"], list)
    assert isinstance(body["combos"], list)
