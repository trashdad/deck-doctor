"""SP8 Deck Doctor tests (completion + cuts)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.doctor import TEMPLATE, category_of, complete_deck, suggest_cuts  # noqa: E402
from app.store import get_store  # noqa: E402
from app.suggest import BANLIST  # noqa: E402

store = get_store()
VALID_ZONES = {"Commanders", "Lands", "Ramp", "Card Draw", "Removal",
               "Board Wipes", "Counters", "Tokens", "Utility"}


def _id(name: str) -> str:
    cid = store._name_to_id.get(name.lower())
    assert cid, f"card not found: {name!r}"
    return cid


def _dragons(n: int) -> list[str]:
    """n real dragons inside Ur-Dragon's identity, by scanning the store."""
    out = []
    for cid, card in store._cards.items():
        tl = card.get("type_line") or ""
        if "Dragon" in tl and "Creature" in tl and "Legendary" not in tl:
            out.append(cid)
        if len(out) >= n:
            break
    return out


def test_complete_reaches_100_deterministic():
    ur = _id("The Ur-Dragon")
    deck = _dragons(5)
    r1 = complete_deck(store, ur, deck)
    r2 = complete_deck(store, ur, deck)
    assert r1["final_size"] == 100
    assert r1 == r2                                   # deterministic
    for a in r1["added"]:
        assert a["zone"] in VALID_ZONES


def test_complete_color_identity_and_banlist():
    # A mono-white EDHREC commander.
    cmd = next(
        (cid for cid in store._edhrec
         if store.get(cid) and set(store.get(cid)["color_identity"]) == {"W"}),
        None,
    )
    assert cmd, "no mono-white EDHREC commander found"
    r = complete_deck(store, cmd, [])
    basics = set()
    for a in r["added"]:
        card = store.get(a["card_id"])
        assert set(card["color_identity"]) <= {"W"}, card["name"]
        assert card["name"] not in BANLIST
        if "Basic" in (card.get("type_line") or ""):
            basics.add(card["name"])
    assert basics <= {"Plains"}


def test_complete_respects_existing_surplus():
    ur = _id("The Ur-Dragon")
    ramp = [cid for cid, c in store._cards.items()
            if category_of(store.get(cid)) == "ramp"
            and set(c.get("color_identity") or []) <= {"W", "U", "B", "R", "G"}][:12]
    r = complete_deck(store, ur, ramp)
    added_ramp = sum(1 for a in r["added"] if category_of(store.get(a["card_id"])) == "ramp")
    assert added_ramp == 0                            # quota already met (deficit 0)
    assert r["final_size"] == 100


def test_basics_follow_pips():
    ur = _id("The Ur-Dragon")
    # Heavy-red nonland seed: red cards with red pips.
    red = [cid for cid, c in store._cards.items()
           if "R" in (c.get("color_identity") or []) and "Land" not in (c.get("type_line") or "")
           and "{R}" in (c.get("mana_cost") or "")][:8]
    r = complete_deck(store, ur, red)
    basic_qty = {}
    for a in r["added"]:
        card = store.get(a["card_id"])
        if "Basic" in (card.get("type_line") or ""):
            basic_qty[card["name"]] = a["quantity"]
    assert basic_qty.get("Mountain", 0) == max(basic_qty.values())


def test_cuts_orders_low_contribution_first():
    ur = _id("The Ur-Dragon")
    dragons = _dragons(10)
    # 2 off-plan mono-white lifegain-ish cards inside CI but off the dragon plan.
    offplan = [cid for cid, c in store._cards.items()
               if set(c.get("color_identity") or []) == {"W"}
               and "Creature" in (c.get("type_line") or "")
               and category_of(store.get(cid)) == "synergy"][:2]
    deck = dragons + offplan
    cuts = suggest_cuts(store, ur, deck, limit=10)
    contribs = [c["contribution"] for c in cuts]
    assert contribs == sorted(contribs)               # ascending (worst first)
    cut_ids = [c["card_id"] for c in cuts]
    assert ur not in cut_ids
    assert all(category_of(store.get(c)) != "land" for c in cut_ids)
    # the off-plan cards should be among the worst few
    assert any(o in cut_ids[:3] for o in offplan)


def test_cuts_protects_complete_combos(tmp_path, monkeypatch):
    from app import config, store as store_module
    from tests.fixtures.spellbook_fixture import make_spellbook_db
    members = make_spellbook_db(tmp_path / "spellbook.sqlite", store)
    monkeypatch.setattr(config, "SPELLBOOK_PATH", tmp_path / "spellbook.sqlite")
    store_module.get_store.cache_clear()
    try:
        s = get_store()
        ur = s._name_to_id["the ur-dragon"]
        a = members["a_members"]                       # complete combo A in-deck
        deck = a + _dragons(5)
        cuts = suggest_cuts(s, ur, deck, limit=30)
        cut_ids = {c["card_id"] for c in cuts}
        assert not (set(a) & cut_ids)                  # combo members protected
    finally:
        store_module.get_store.cache_clear()
