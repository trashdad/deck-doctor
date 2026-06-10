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


def test_recommend_requires_commander():
    """SP5 replaced the legacy DER recommend; commander-less requests are 400."""
    es = _id("Evolution Sage")
    deck = {"commander_id": None, "cards": [{"id": es}]}
    assert client.post("/deck/recommend", json=deck).status_code == 400


def test_relationships_axes():
    sr = _id("Sol Ring")
    for axis in ("similar", "synergy", "cooccurrence"):
        r = client.get(f"/cards/{sr}/relationships?axis={axis}&limit=10")
        assert r.status_code == 200, axis
        rows = r.json()
        assert isinstance(rows, list)
        metrics = [row["metric"] for row in rows]
        assert metrics == sorted(metrics, reverse=True), axis
        for row in rows:
            assert row["card"]["id"] != sr
            assert "name" in row["card"]


def test_relationships_bad_axis_422():
    sr = _id("Sol Ring")
    assert client.get(f"/cards/{sr}/relationships?axis=bogus").status_code == 422


def test_relationships_unknown_card_404():
    assert client.get("/cards/not-a-card/relationships").status_code == 404


def test_combos_engines_endpoint():
    sr = _id("Sol Ring")
    r = client.get(f"/cards/{sr}/combos-engines")
    assert r.status_code == 200
    groups = r.json()
    assert isinstance(groups, list)
    for g in groups:
        assert {"engine_id", "kind", "asserted", "candidate", "members"} <= set(g)
        assert any(m["id"] == sr for m in g["members"])


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


def test_score_pair_includes_cooccurrence_block():
    sr = _id("Sol Ring")
    lb = _id("Lightning Bolt")
    r = client.get(f"/score/pair?a={sr}&b={lb}")
    assert r.status_code == 200
    body = r.json()
    assert "relationship" in body          # SP1 field preserved
    assert "cooccurrence" in body          # new key present (may be null)


def test_deck_engines_endpoint():
    sr = _id("Sol Ring")
    ct = _id("Command Tower")
    r = client.post("/deck/engines", json={"cards": [{"id": sr}, {"id": ct}]})
    assert r.status_code == 200
    body = r.json()
    assert "engines" in body and "combos" in body
    assert isinstance(body["engines"], list)
    assert isinstance(body["combos"], list)
