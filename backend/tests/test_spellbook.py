"""SP7 Commander Spellbook integration tests (fixture DB, no network)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import store as store_module  # noqa: E402
from app.main import app  # noqa: E402
from app.store import get_store  # noqa: E402
from app.suggest import recommend  # noqa: E402
from tests.fixtures.spellbook_fixture import (  # noqa: E402
    restore_spellbook_pg, seed_spellbook_pg)

client = TestClient(app)


@pytest.fixture
def fx():
    """Swap a 2-combo fixture into Postgres + a fresh Store; restore after."""
    real = get_store()                       # resolve fixture names via the real index
    members = seed_spellbook_pg(real)
    store_module.get_store.cache_clear()
    yield {"store": get_store(), "members": members}
    restore_spellbook_pg()
    store_module.get_store.cache_clear()     # next access rebuilds the real store


def test_load_skips_unresolvable(fx):
    # fxC contains "Nonexistent Card XYZ" → skipped; fxA + fxB load → 2.
    assert len(fx["store"]._spellbook) == 2


def test_deck_combos_complete_and_near(fx):
    a = fx["members"]["a_members"]
    b = fx["members"]["b_members"]
    deck = a + b[:2]                           # all of A + 2 of B (exactly 1 missing)
    res = fx["store"].deck_spellbook(deck)
    complete_ids = {c["combo_id"] for c in res["complete"]}
    near = {n["combo"]["combo_id"]: n["missing"] for n in res["near"]}
    assert "fxA" in complete_ids
    assert "fxB" in near
    assert near["fxB"] == b[2]                  # the one missing B member


def test_suggest_spellbook_completion(fx):
    store = fx["store"]
    a = fx["members"]["a_members"]
    cmd = store._name_to_id["the ur-dragon"]   # WUBRG ⊇ colorless combo A
    res = recommend(store, cmd, [a[0]], limit=80, explain=True)
    by_id = {s["card"]["id"]: s for s in res["suggestions"]}
    assert a[1] in by_id, "missing combo piece not suggested"
    reasons = by_id[a[1]]["reasons"]
    engine = next((r for r in reasons if r["signal"] == "engine"), None)
    assert engine is not None
    assert "Infinite mana" in engine["detail"]
    assert engine["value"] == 1.2              # SPELLBOOK_BONUS > mined engine 1.0


def test_spellbook_endpoint_shapes(fx):
    sr = fx["store"]._name_to_id["sol ring"]   # in fixture combo A
    r = client.get(f"/cards/{sr}/spellbook-combos")
    assert r.status_code == 200
    combos = r.json()
    assert any(c["combo_id"] == "fxA" for c in combos)
    pops = [c["popularity"] for c in combos if c["popularity"] is not None]
    assert pops == sorted(pops, reverse=True)
    for c in combos:
        assert all("name" in m for m in c["members"])
    assert client.get("/cards/not-a-card/spellbook-combos").status_code == 404


def _commander_with_ci(store, ci: set[str]) -> str:
    from app.suggest import is_commander
    for cid, card in store._cards.items():
        if set(card.get("color_identity") or []) == ci and is_commander(card):
            return cid
    pytest.skip(f"no commander with identity {sorted(ci)} in the store")


def _near_ids(commander_id, deck_ids) -> set[str]:
    body = {"commander_id": commander_id, "cards": [{"id": c} for c in deck_ids]}
    r = client.post("/deck/combos", json=body)
    assert r.status_code == 200
    return {n["combo"]["combo_id"] for n in r.json()["near"]}


def test_deck_combos_near_respects_commander_identity(fx):
    # Real-data regression: a mono-red Krenko deck was told it was "one card away"
    # from combos needing Food Chain (G) / Hullbreaker Horror (U).
    store = fx["store"]
    b = fx["members"]["b_members"]             # Bolt (R), Counterspell (U), Llanowar Elves (G)
    deck = b[:2]                               # the missing piece is the green Elves
    izzet = _commander_with_ci(store, {"U", "R"})
    assert "fxB" not in _near_ids(izzet, deck)  # can't legally add a green card
    ur = store._name_to_id["the ur-dragon"]
    assert "fxB" in _near_ids(ur, deck)        # 5-colour commander: still one away


def test_deck_combos_near_skips_banned_missing_piece(fx, monkeypatch):
    # Real-data regression: Sway of the Stars (banned) was offered as a missing piece.
    monkeypatch.setattr("app.suggest.BANLIST", frozenset({"Llanowar Elves"}))
    b = fx["members"]["b_members"]
    ur = fx["store"]._name_to_id["the ur-dragon"]
    assert "fxB" not in _near_ids(ur, b[:2])



def _named(store, name):
    cid = store._name_to_id.get(name.lower())
    if cid is None:
        pytest.skip(f"{name!r} not in the card pool")
    return cid


def _near(body) -> set[str]:
    r = client.post("/deck/combos", json=body)
    assert r.status_code == 200
    return {n["combo"]["combo_id"] for n in r.json()["near"]}


def test_deck_combos_partner_identity_is_the_union(fx):
    """Review #3: partners send the 2nd commander in cards with zone "Commanders";
    the identity is the union (Tymna WB + Kraum UR)."""
    store = fx["store"]
    b = fx["members"]["b_members"]             # Bolt (R), Counterspell (U), Elves (G)
    tymna = _named(store, "Tymna the Weaver")
    kraum = _named(store, "Kraum, Ludevic's Opus")
    deck = [{"id": b[0]}, {"id": b[2]}]        # missing piece: Counterspell (U)
    assert "fxB" in _near({"commander_id": tymna,
                           "cards": deck + [{"id": kraum, "zone": "Commanders"}]})
    assert "fxB" not in _near({"commander_id": tymna, "cards": deck})   # WB alone


def test_deck_combos_non_creature_commander_still_restricts(fx):
    """Review #4: a commander that is not a legendary creature/planeswalker (Shorikai,
    a Vehicle, identity WU) must still restrict instead of disabling the filter."""
    store = fx["store"]
    b = fx["members"]["b_members"]
    shorikai = _named(store, "Shorikai, Genesis Engine")
    assert "fxB" not in _near({"commander_id": shorikai,
                               "cards": [{"id": b[0]}, {"id": b[1]}]})   # needs Elves (G)


def test_deck_combos_without_commander_keeps_identity_open(fx):
    b = fx["members"]["b_members"]
    assert "fxB" in _near({"commander_id": None, "cards": [{"id": b[0]}, {"id": b[1]}]})
