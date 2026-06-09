import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build_relationships import build  # noqa: E402


def _seed_db(db, cards, fingerprints):
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE cards (id TEXT PRIMARY KEY, name TEXT, cmc REAL, type_line TEXT, "
                "colors TEXT, color_identity TEXT, image_normal TEXT, ier REAL, "
                "mechanic_tags TEXT, parasitic TEXT)")
    for cid, name in cards:
        con.execute("INSERT INTO cards (id, name) VALUES (?,?)", (cid, name))
    con.execute("CREATE TABLE card_fingerprints (card_id TEXT, ability_idx INT, record TEXT, "
                "source TEXT, confidence REAL, PRIMARY KEY(card_id, ability_idx))")
    con.execute("CREATE TABLE card_flat_tags (card_id TEXT PRIMARY KEY, tags TEXT)")
    for cid, recs in fingerprints.items():
        for r in recs:
            con.execute("INSERT INTO card_fingerprints VALUES (?,?,?,?,?)",
                        (cid, r["ability_idx"], json.dumps(r), "mtgish", 1.0))
        con.execute("INSERT INTO card_flat_tags VALUES (?,?)", (cid, json.dumps([])))
    con.commit(); con.close()


def _eff(verb):
    return {"verb": verb, "object": None, "prefixes": [], "scope": None,
            "quantifier": None, "targeted": False, "counter": None, "amount": None,
            "duration": None, "grants": None, "optional": False, "sub_effects": []}


def test_build_writes_relationship_and_engine_tables(tmp_path):
    # A 3-card aristocrats chain: maker (tokens=fodder) -> outlet (sac -> death)
    # -> aristocrat (dies-trigger). Validates both the typed pair edges and the
    # k>=3 engine persistence (k<=2 chains live only in card_relationships).
    db = str(tmp_path / "scores.sqlite")
    cards = [("id-maker", "Maker"), ("id-outlet", "Outlet"), ("id-aristocrat", "Aristocrat")]
    fps = {
        "id-maker": [{"ability_idx": 0, "kind": "spell", "trigger": None, "cost": None,
                      "condition": None, "optional": False, "modal": None,
                      "effects": [_eff("CreateTokens")], "raw": {}}],
        "id-outlet": [{"ability_idx": 0, "kind": "activated", "trigger": None,
                       "cost": {"sacrifice": True}, "condition": None, "optional": False,
                       "modal": None, "effects": [_eff("DrawACard")], "raw": {}}],
        "id-aristocrat": [{"ability_idx": 0, "kind": "triggered",
                           "trigger": {"op": "WhenACreatureOrPlaneswalkerDies"}, "cost": None,
                           "condition": None, "optional": False, "modal": None,
                           "effects": [_eff("LoseLife")], "raw": {}}],
    }
    _seed_db(db, cards, fps)

    stats = build(db, catalog_paths=[], kmax=3)

    con = sqlite3.connect(db)
    # maker produces sacrifice_fodder, outlet consumes it -> directed synergy edge
    a, b = sorted(["id-maker", "id-outlet"])
    syn = con.execute("SELECT synergy_ab, synergy_ba FROM card_relationships WHERE a=? AND b=?",
                      (a, b)).fetchone()
    assert syn is not None and max(syn) > 0.0
    # the 3-card chain is stored as an engine (k>=3)
    n_eng = con.execute("SELECT COUNT(*) FROM engines WHERE kind='chain'").fetchone()[0]
    assert n_eng >= 1
    con.close()
    assert stats["pairs"] >= 1
