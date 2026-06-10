"""SP9 deck graph endpoint tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.graph import (DEGREE_CAP, LIFT_EDGE_MIN, SYNERGY_EDGE_MIN, deck_graph)  # noqa: E402
from app.store import get_store  # noqa: E402
from app.suggest import lift_to_norm  # noqa: E402

store = get_store()
VALID_CATEGORIES = {"commander", "land", "ramp", "card_draw", "removal",
                    "board_wipe", "counters", "tokens", "synergy"}


def _id(name: str) -> str:
    cid = store._name_to_id.get(name.lower())
    assert cid, f"card not found: {name!r}"
    return cid


def _sample_deck(n: int) -> list[str]:
    """First n resolvable nonland cards in WUBRG-ish identity (dragons + staples)."""
    out = []
    for cid, card in store._cards.items():
        if "Dragon" in (card.get("type_line") or "") and "Creature" in (card.get("type_line") or ""):
            out.append(cid)
        if len(out) >= n:
            break
    return out


def test_graph_nodes_match_deck():
    ur = _id("The Ur-Dragon")
    deck = _sample_deck(20)
    g = deck_graph(store, ur, deck)
    node_ids = {n["id"] for n in g["nodes"]}
    assert node_ids == set(deck) | {ur}
    assert all(n["category"] in VALID_CATEGORIES for n in g["nodes"])
    for e in g["edges"]:
        assert e["a"] in node_ids and e["b"] in node_ids
        assert e["a"] < e["b"]


def test_graph_thresholds():
    ur = _id("The Ur-Dragon")
    g = deck_graph(store, ur, _sample_deck(30))
    cooc_min = lift_to_norm(LIFT_EDGE_MIN)
    for e in g["edges"]:
        if e["kind"] == "synergy":
            assert e["weight"] >= SYNERGY_EDGE_MIN - 1e-9
        elif e["kind"] == "cooccurrence":
            assert e["weight"] >= cooc_min - 1e-9
        elif e["kind"] == "combo":
            assert e["weight"] == 1.0


def test_graph_combo_edges(tmp_path, monkeypatch):
    from app import config, store as store_module
    from tests.fixtures.spellbook_fixture import make_spellbook_db
    members = make_spellbook_db(tmp_path / "spellbook.sqlite", store)
    monkeypatch.setattr(config, "SPELLBOOK_PATH", tmp_path / "spellbook.sqlite")
    store_module.get_store.cache_clear()
    try:
        s = get_store()
        ur = s._name_to_id["the ur-dragon"]
        a = members["a_members"]                       # complete combo A
        g = deck_graph(s, ur, a)
        combo_edges = [(e["a"], e["b"]) for e in g["edges"] if e["kind"] == "combo"]
        lo, hi = sorted(a)
        assert (lo, hi) in combo_edges
        assert all(e["weight"] == 1.0 for e in g["edges"] if e["kind"] == "combo")
    finally:
        store_module.get_store.cache_clear()


def test_graph_degree_cap():
    ur = _id("The Ur-Dragon")
    g = deck_graph(store, ur, _sample_deck(60))
    degree: dict[str, int] = {}
    for e in g["edges"]:
        degree[e["a"]] = degree.get(e["a"], 0) + 1
        degree[e["b"]] = degree.get(e["b"], 0) + 1
    # soft cap: an endpoint may exceed DEGREE_CAP via under-cap partners, but never wildly.
    assert max(degree.values(), default=0) <= DEGREE_CAP + 4
