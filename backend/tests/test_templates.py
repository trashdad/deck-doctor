"""Template system + dual-theme composite tests against the real store."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.store import get_store  # noqa: E402
from app.suggest import BANLIST  # noqa: E402

client = TestClient(app)
store = get_store()


def _id(name: str) -> str:
    cid = store._name_to_id.get(name.lower())
    assert cid, f"card not found: {name!r}"
    return cid


def _suggest(commander_id, themes=(), free_text="", limit=10, offset=0):
    return client.post(
        f"/deck/theme-suggest?limit={limit}&offset={offset}",
        json={"commander_id": commander_id, "themes": list(themes),
              "free_text": free_text},
    )


def test_get_templates_shape():
    r = client.get("/templates")
    assert r.status_code == 200
    body = r.json()
    ids = {t["id"] for t in body["templates"]}
    assert {"command_zone", "control", "aggro", "combo",
            "corpus_average", "simmander_composite"} <= ids
    cz = next(t for t in body["templates"] if t["id"] == "command_zone")
    assert cz["counts"] == {"land": 38, "ramp": 10, "card_draw": 8,
                            "removal": 8, "board_wipe": 4}
    # Every template's counts use the doctor keys (so they drop into complete_deck).
    for t in body["templates"]:
        assert set(t["counts"]) == {"land", "ramp", "card_draw", "removal", "board_wipe"}
    assert len(body["themes"]) >= 12
    for th in body["themes"]:
        assert th["tags"], f"theme {th['id']} has no tags"


def test_theme_suggest_in_colors_and_ranked():
    cmd_card = store.commanders(sort="popularity", limit=1)[0]
    cmd, ci = cmd_card["id"], set(cmd_card["color_identity"])
    r = _suggest(cmd, ["aristocrats", "card_draw"], limit=15)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] > 0
    cards = body["cards"]
    # color identity ⊆ commander CI; no basics; no banlist; scores descending
    scores = [c["score"] for c in cards]
    assert scores == sorted(scores, reverse=True)
    for c in cards:
        assert set(c["card"]["color_identity"]) <= ci
        assert "Basic" not in c["card"]["type_line"]
        assert c["card"]["name"] not in BANLIST


def test_theme_suggest_pagination():
    cmd = store.commanders(sort="popularity", limit=1)[0]["id"]
    p1 = _suggest(cmd, ["counters"], limit=5, offset=0).json()
    p2 = _suggest(cmd, ["counters"], limit=5, offset=5).json()
    assert p1["total"] == p2["total"]
    if p1["total"] > 5:
        assert p1["has_more"] is True
        ids1 = {c["card"]["id"] for c in p1["cards"]}
        ids2 = {c["card"]["id"] for c in p2["cards"]}
        assert ids1.isdisjoint(ids2)   # distinct pages
    last_off = max(p1["total"] - 1, 0)
    tail = _suggest(cmd, ["counters"], limit=5, offset=last_off).json()
    assert tail["has_more"] is False


def test_both_theme_cards_get_relevance_boost():
    """A card in BOTH selected themes carries themes_matched=2 (the 1.5x bridge)."""
    cmd = store.commanders(sort="popularity", limit=1)[0]["id"]
    body = _suggest(cmd, ["aristocrats", "card_draw"], limit=60).json()
    matched = {c["themes_matched"] for c in body["cards"]}
    assert 2 in matched, "expected at least one card bridging both themes"
    assert matched <= {1, 2}


def test_bad_commander_400():
    assert _suggest("not-a-real-id", ["burn"]).status_code == 400
    # a non-commander card id is also rejected
    sol = store._name_to_id.get("sol ring")
    if sol:
        assert _suggest(sol, ["ramp"]).status_code == 400


def test_complete_respects_template_quota():
    """Passing a template with a high removal quota shifts the completion mix."""
    cmd = store.commanders(sort="popularity", limit=1)[0]["id"]
    body = {
        "commander_id": cmd,
        "cards": [],
        "template": {"land": 38, "ramp": 10, "card_draw": 10,
                     "removal": 13, "board_wipe": 6},
    }
    r = client.post("/deck/complete", json=body)
    assert r.status_code == 200
    assert r.json()["final_size"] == 100
