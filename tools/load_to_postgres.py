"""Load the offline SQLite build artifacts into the deckdoctor Postgres database.

The scoring/ pipeline + the scrapers emit SQLite files (data/*.sqlite) as the
deterministic, stdlib-only build output. This step mirrors those tables into
Postgres — which is what the running app actually reads. Run it after a rebuild
(or after rsyncing fresh artifacts onto a box):

    python tools/load_to_postgres.py
    python tools/load_to_postgres.py --database-url postgresql://user:pw@host/deckdoctor

Idempotent: each analytical table is dropped, recreated, and reloaded. JSON-ish
columns stay TEXT so the backend's json.loads(...) call-sites are unchanged. The
corpus decks/deck_cards tables are renamed corpus_decks/corpus_deck_cards so they
don't collide with the read-write userdecks tables (decks/deck_cards) that live in
the same database and are owned by backend/app/decks.py — which this never touches.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

# store label -> sqlite file. Every user table in each file is loaded.
STORES = {
    "scores": DATA / "scores.sqlite",
    "edhrec": DATA / "edhrec.sqlite",
    "decks": DATA / "decks.sqlite",
    "spellbook": DATA / "spellbook.sqlite",
}

# (store, sqlite_table) -> postgres table name, to dodge the userdecks collision.
RENAME = {
    ("decks", "decks"): "corpus_decks",
    ("decks", "deck_cards"): "corpus_deck_cards",
}

# Indexes the Store's per-request reads depend on (created after load).
INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_cards_id ON cards(id)",
    "CREATE INDEX IF NOT EXISTS idx_syn_a ON synergies(card_a)",
    "CREATE INDEX IF NOT EXISTS idx_syn_b ON synergies(card_b)",
    "CREATE INDEX IF NOT EXISTS idx_rel_a ON card_relationships(a)",
    "CREATE INDEX IF NOT EXISTS idx_rel_b ON card_relationships(b)",
    "CREATE INDEX IF NOT EXISTS idx_cooc_a ON card_cooccurrence(a)",
    "CREATE INDEX IF NOT EXISTS idx_cooc_b ON card_cooccurrence(b)",
    "CREATE INDEX IF NOT EXISTS idx_edhrec_cmd ON edhrec_metrics(commander)",
    "CREATE INDEX IF NOT EXISTS idx_corpus_decks_cmd ON corpus_decks(commander)",
    "CREATE INDEX IF NOT EXISTS idx_combo_cards_combo ON combo_cards(combo_id)",
    "CREATE INDEX IF NOT EXISTS idx_combo_cards_name ON combo_cards(card_name)",
    "CREATE INDEX IF NOT EXISTS idx_tag_inv_tag ON tag_inverted_index(tag)",
]


def pg_type(sqlite_decl: str) -> str:
    d = (sqlite_decl or "").upper()
    if "INT" in d:
        return "BIGINT"
    if any(x in d for x in ("REAL", "FLOA", "DOUB", "NUMERIC")):
        return "DOUBLE PRECISION"
    if "BLOB" in d:
        return "BYTEA"
    return "TEXT"  # TEXT + anything JSON-ish stays text


def load_table(scur, pcur, store: str, table: str) -> int:
    cols = scur.execute(f"PRAGMA table_info({table})").fetchall()
    if not cols:
        return 0
    names = [c[1] for c in cols]
    decls = [pg_type(c[2]) for c in cols]
    pg_table = RENAME.get((store, table), table)

    pcur.execute(f'DROP TABLE IF EXISTS "{pg_table}"')
    coldefs = ", ".join(f'"{n}" {t}' for n, t in zip(names, decls))
    pcur.execute(f'CREATE TABLE "{pg_table}" ({coldefs})')

    collist = ", ".join(f'"{n}"' for n in names)
    insert = f'INSERT INTO "{pg_table}" ({collist}) VALUES %s'
    total = 0
    batch: list[tuple] = []
    for row in scur.execute(f"SELECT {collist} FROM {table}"):
        batch.append(tuple(row))
        if len(batch) >= 5000:
            execute_values(pcur, insert, batch, page_size=5000)
            total += len(batch)
            batch = []
    if batch:
        execute_values(pcur, insert, batch, page_size=5000)
        total += len(batch)
    return total


def main() -> int:
    ap = argparse.ArgumentParser(description="Mirror SQLite build artifacts into Postgres.")
    ap.add_argument("--database-url",
                    default=os.environ.get("DATABASE_URL",
                                           "postgresql://deckdoctor:deckdoctor@localhost:5432/deckdoctor"))
    ap.add_argument("--data", default=str(DATA), help="dir holding the *.sqlite artifacts")
    args = ap.parse_args()

    data_dir = Path(args.data)
    pconn = psycopg2.connect(args.database_url)
    pconn.autocommit = False
    pcur = pconn.cursor()

    grand = 0
    for store, default_path in STORES.items():
        path = data_dir / default_path.name
        if not path.exists():
            print(f"[skip] {store}: {path} not found", file=sys.stderr)
            continue
        sconn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        scur = sconn.cursor()
        tables = [r[0] for r in scur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        for t in tables:
            n = load_table(scur, pcur, store, t)
            pg_table = RENAME.get((store, t), t)
            grand += n
            print(f"  {store}.{t:<22} -> {pg_table:<22} {n:>9,} rows")
        sconn.close()
        pconn.commit()

    for stmt in INDEXES:
        try:
            pcur.execute(stmt)
        except psycopg2.Error as e:
            print(f"[index] skip ({e})", file=sys.stderr)
            pconn.rollback()
    pconn.commit()
    pcur.close()
    pconn.close()
    print(f"loaded {grand:,} rows into Postgres ({args.database_url.rsplit('@', 1)[-1]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
