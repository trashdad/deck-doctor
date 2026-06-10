"""SP7 test fixture — build a tiny synthetic spellbook.sqlite over REAL card names.

make_spellbook_db(path, store) creates a spellbook.sqlite (load_spellbook schema) with:
  combo "fxA": 2 colorless cards, produces ["Infinite mana"], popularity 100
  combo "fxB": 3 cards, produces ["Infinite draw"], popularity 50
  combo "fxC": 1 real card + a fake name (must be skipped at Store load)
Returns {"a_members": [ids], "b_members": [ids]} for tests to assert against.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE combos (
    combo_id TEXT PRIMARY KEY, identity TEXT, popularity INTEGER, bracket_tag TEXT,
    description TEXT, mana_needed TEXT, easy_prereq TEXT, notable_prereq TEXT,
    produces TEXT NOT NULL, card_count INTEGER NOT NULL);
CREATE TABLE combo_cards (
    combo_id TEXT NOT NULL, card_name TEXT NOT NULL, quantity INTEGER NOT NULL DEFAULT 1,
    must_be_commander INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (combo_id, card_name));
CREATE INDEX idx_combo_cards_name ON combo_cards(card_name);
"""

# Real, ubiquitous names — assert-resolved below so a missing one fails loudly.
A_NAMES = ["Sol Ring", "Mana Vault"]
B_NAMES = ["Lightning Bolt", "Counterspell", "Llanowar Elves"]
C_NAMES = ["Command Tower", "Nonexistent Card XYZ"]


def _name_id(store, name: str) -> str:
    cid = store._name_to_id.get(name.lower())
    assert cid, f"fixture needs {name!r} in the live store"
    return cid


def make_spellbook_db(path: Path, store) -> dict:
    con = sqlite3.connect(path)
    con.executescript(_SCHEMA)
    combos = [
        ("fxA", "", 100, json.dumps(["Infinite mana"]), A_NAMES),
        ("fxB", "GUR", 50, json.dumps(["Infinite draw"]), B_NAMES),
        ("fxC", "", 10, json.dumps(["Win the game"]), C_NAMES),
    ]
    for combo_id, identity, pop, produces, names in combos:
        con.execute(
            "INSERT INTO combos (combo_id, identity, popularity, bracket_tag, description, "
            "mana_needed, easy_prereq, notable_prereq, produces, card_count) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (combo_id, identity, pop, "", f"{combo_id} desc", "", "", "", produces, len(names)),
        )
        con.executemany(
            "INSERT INTO combo_cards (combo_id, card_name, quantity, must_be_commander) "
            "VALUES (?,?,1,0)", [(combo_id, n) for n in names])
    con.commit()
    con.close()
    return {
        "a_members": [_name_id(store, n) for n in A_NAMES],
        "b_members": [_name_id(store, n) for n in B_NAMES],
    }
