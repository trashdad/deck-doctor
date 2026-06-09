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


def test_build_writes_relationship_and_engine_tables(tmp_path):
    db = str(tmp_path / "scores.sqlite")
    cards = [("id-maker", "Maker"), ("id-payoff", "Payoff")]
    fps = {
        "id-maker": [{"ability_idx": 0, "kind": "spell", "trigger": None, "cost": None,
                      "condition": None, "optional": False, "modal": None,
                      "effects": [{"verb": "CreateTokens", "object": None, "prefixes": [],
                                   "scope": None, "quantifier": None, "targeted": False,
                                   "counter": None, "amount": None, "duration": None,
                                   "grants": None, "optional": False, "sub_effects": []}],
                      "raw": {}}],
        "id-payoff": [{"ability_idx": 0, "kind": "triggered",
                       "trigger": {"op": "WhenATokenIsCreated"}, "cost": None,
                       "condition": None, "optional": False, "modal": None,
                       "effects": [], "raw": {}}],
    }
    _seed_db(db, cards, fps)

    stats = build(db, catalog_paths=[], kmax=3)

    con = sqlite3.connect(db)
    row = con.execute("SELECT synergy_ab, synergy_ba, similarity FROM card_relationships "
                      "WHERE a=? AND b=?", tuple(sorted(["id-maker", "id-payoff"]))).fetchone()
    assert row is not None
    a, b = sorted(["id-maker", "id-payoff"])
    # maker produces token, payoff consumes token -> directed synergy from maker
    syn = con.execute("SELECT synergy_ab, synergy_ba FROM card_relationships WHERE a=? AND b=?",
                      (a, b)).fetchone()
    assert max(syn) > 0.0
    n_eng = con.execute("SELECT COUNT(*) FROM engines").fetchone()[0]
    assert n_eng >= 1
    con.close()
    assert stats["pairs"] >= 1
