"""SP6 — user deck persistence in Postgres (the deckdoctor database, read-WRITE).

The only mutable data in the app. Tables `decks` / `deck_cards` live in the same
Postgres database as the read-only analytical tables (which are named
corpus_*/cards/etc., so there is no collision). Postgres handles concurrency, so
no app-level lock is needed; each call borrows a pooled connection. Saving cards
is a FULL REPLACE inside one transaction. Timestamps are stored as ISO-8601 TEXT
to keep the JSON contract identical to the previous SQLite implementation.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from functools import lru_cache

from . import db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS decks (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    commander_id TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS deck_cards (
    deck_id  TEXT NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    card_id  TEXT NOT NULL,
    zone     TEXT NOT NULL DEFAULT 'Utility',
    quantity INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (deck_id, card_id)
);
"""


class UserDecks:
    def __init__(self) -> None:
        with db.cursor(commit=True) as cur:
            cur.execute(_SCHEMA)
            cur.execute("ALTER TABLE decks ADD COLUMN IF NOT EXISTS user_id INTEGER")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_decks_user ON decks(user_id)")

    # ---- reads -----------------------------------------------------------
    def list_decks(self, user_id: int) -> list[dict]:
        with db.cursor() as cur:
            cur.execute(
                """
                SELECT d.id, d.name, d.commander_id, d.updated_at,
                       COALESCE(SUM(c.quantity), 0) AS card_count
                FROM decks d
                LEFT JOIN deck_cards c ON c.deck_id = d.id
                WHERE d.user_id = %s
                GROUP BY d.id
                ORDER BY d.updated_at DESC
                """,
                (user_id,))
            rows = cur.fetchall()
        return [
            {"id": r[0], "name": r[1], "commander_id": r[2],
             "updated_at": r[3], "card_count": int(r[4])}
            for r in rows
        ]

    def get(self, deck_id: str, user_id: int) -> dict | None:
        with db.cursor() as cur:
            cur.execute(
                "SELECT id, name, commander_id, created_at, updated_at "
                "FROM decks WHERE id=%s AND user_id=%s", (deck_id, user_id))
            row = cur.fetchone()
            if row is None:
                return None
            cur.execute(
                "SELECT card_id, zone, quantity FROM deck_cards WHERE deck_id=%s",
                (deck_id,))
            cards = cur.fetchall()
        return {
            "id": row[0], "name": row[1], "commander_id": row[2],
            "created_at": row[3], "updated_at": row[4],
            "cards": [{"card_id": c[0], "zone": c[1], "quantity": c[2]} for c in cards],
        }

    # ---- writes ----------------------------------------------------------
    def _write_cards(self, cur, deck_id: str, cards: list[dict]) -> None:
        cur.execute("DELETE FROM deck_cards WHERE deck_id=%s", (deck_id,))
        if cards:
            cur.executemany(
                "INSERT INTO deck_cards (deck_id, card_id, zone, quantity) VALUES (%s,%s,%s,%s)",
                [(deck_id, c.get("id") or c["card_id"], c.get("zone", "Utility"),
                  int(c.get("quantity", 1))) for c in cards])

    def create(self, user_id: int, name: str, commander_id: str | None,
               cards: list[dict]) -> str:
        deck_id = uuid.uuid4().hex
        ts = _now()
        with db.cursor(commit=True) as cur:
            cur.execute(
                "INSERT INTO decks (id, user_id, name, commander_id, created_at, updated_at) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (deck_id, user_id, name, commander_id, ts, ts))
            self._write_cards(cur, deck_id, cards)
        return deck_id

    def update(self, deck_id: str, user_id: int, name: str,
               commander_id: str | None, cards: list[dict]) -> bool:
        with db.cursor(commit=True) as cur:
            cur.execute("SELECT 1 FROM decks WHERE id=%s AND user_id=%s", (deck_id, user_id))
            if cur.fetchone() is None:
                return False
            cur.execute(
                "UPDATE decks SET name=%s, commander_id=%s, updated_at=%s "
                "WHERE id=%s AND user_id=%s",
                (name, commander_id, _now(), deck_id, user_id))
            self._write_cards(cur, deck_id, cards)
        return True

    def delete(self, deck_id: str, user_id: int) -> bool:
        with db.cursor(commit=True) as cur:
            cur.execute("DELETE FROM decks WHERE id=%s AND user_id=%s", (deck_id, user_id))
            return cur.rowcount > 0


@lru_cache(maxsize=1)
def get_userdecks() -> UserDecks:
    return UserDecks()
