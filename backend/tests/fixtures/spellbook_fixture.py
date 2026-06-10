"""SP7 test fixture — seed a tiny synthetic spellbook into Postgres over REAL names.

The app reads combos from Postgres, so tests can't point it at a throwaway SQLite
file any more. Instead we swap the real combos/combo_cards tables ASIDE (instant
metadata rename), stand up a 2-combo fixture, run the test, then swap the real
tables back. Fixture combos:

  combo "fxA": 2 colorless cards, produces ["Infinite mana"], popularity 100
  combo "fxB": 3 cards,           produces ["Infinite draw"], popularity 50
  combo "fxC": 1 real card + a fake name  → skipped at Store load (so 2 load)

seed_spellbook_pg(store) returns {"a_members": [...], "b_members": [...]}.
restore_spellbook_pg() puts the real tables back. Both are idempotent.
"""

from __future__ import annotations

import json

from app import db

A_NAMES = ["Sol Ring", "Mana Vault"]
B_NAMES = ["Lightning Bolt", "Counterspell", "Llanowar Elves"]
C_NAMES = ["Command Tower", "Nonexistent Card XYZ"]

# (combo_id, identity, popularity, produces-json, [names])
_COMBOS = [
    ("fxA", "", 100, json.dumps(["Infinite mana"]), A_NAMES),
    ("fxB", "GUR", 50, json.dumps(["Infinite draw"]), B_NAMES),
    ("fxC", "", 10, json.dumps(["Win the game"]), C_NAMES),
]


def _name_id(store, name: str) -> str:
    cid = store._name_to_id.get(name.lower())
    assert cid, f"fixture needs {name!r} in the live store"
    return cid


def _restore_if_stashed(cur) -> None:
    cur.execute("SELECT to_regclass('combos_real')")
    if cur.fetchone()[0] is not None:
        cur.execute("DROP TABLE IF EXISTS combos, combo_cards")
        cur.execute("ALTER TABLE combos_real RENAME TO combos")
        cur.execute("ALTER TABLE combo_cards_real RENAME TO combo_cards")


def seed_spellbook_pg(store) -> dict:
    from tests.conftest import assert_safe_destructive_db
    assert_safe_destructive_db()                       # never rename live prod tables
    with db.cursor(commit=True) as cur:
        _restore_if_stashed(cur)                       # clean up any prior crash
        cur.execute("ALTER TABLE combos RENAME TO combos_real")
        cur.execute("ALTER TABLE combo_cards RENAME TO combo_cards_real")
        cur.execute(
            "CREATE TABLE combos (combo_id TEXT, identity TEXT, popularity BIGINT, "
            "bracket_tag TEXT, description TEXT, mana_needed TEXT, produces TEXT)")
        cur.execute("CREATE TABLE combo_cards (combo_id TEXT, card_name TEXT)")
        for combo_id, identity, pop, produces, names in _COMBOS:
            cur.execute(
                "INSERT INTO combos (combo_id, identity, popularity, bracket_tag, "
                "description, mana_needed, produces) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (combo_id, identity, pop, "", f"{combo_id} desc", "", produces))
            cur.executemany(
                "INSERT INTO combo_cards (combo_id, card_name) VALUES (%s,%s)",
                [(combo_id, n) for n in names])
    return {
        "a_members": [_name_id(store, n) for n in A_NAMES],
        "b_members": [_name_id(store, n) for n in B_NAMES],
    }


def restore_spellbook_pg() -> None:
    from tests.conftest import assert_safe_destructive_db
    assert_safe_destructive_db()
    with db.cursor(commit=True) as cur:
        _restore_if_stashed(cur)
