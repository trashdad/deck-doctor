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


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_search_by_name():
    names = [c["name"] for c in client.get("/cards?q=rhystic").json()]
    assert "Rhystic Study" in names


def test_search_by_color_identity():
    cards = client.get("/cards?colors=G").json()
    assert cards and all("G" in c["color_identity"] for c in cards)


def test_pair_score_counter_engine():
    r = client.get("/score/pair?a=evolution-sage&b=hardened-scales").json()
    assert r["css"] >= 2.0          # complementary counter engine
    assert r["der"] > r["ier_a"] + r["ier_b"]  # synergy term applied


def test_pair_score_unknown_card_404():
    assert client.get("/score/pair?a=nope&b=hardened-scales").status_code == 404


def test_deck_analyze_shapes():
    deck = {
        "commander_id": "chatterfang",
        "cards": [
            {"id": "chatterfang"}, {"id": "doubling-season"},
            {"id": "evolution-sage"}, {"id": "hardened-scales"},
            {"id": "sol-ring"}, {"id": "command-tower"},
        ],
    }
    a = client.post("/deck/analyze", json=deck).json()
    assert a["card_count"] == 6
    assert 0 <= a["efficiency"] <= 10
    assert 0 <= a["score"] <= 1000
    assert 1 <= a["bracket"] <= 5
    assert isinstance(a["mana_curve"], list)


def test_recommend_excludes_in_deck():
    deck = {"commander_id": None, "cards": [{"id": "evolution-sage"}]}
    recs = client.post("/deck/recommend", json=deck).json()
    in_deck = {"evolution-sage"}
    for e in recs:
        assert not ({e["card_a"], e["card_b"]} <= in_deck)
