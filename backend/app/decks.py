"""SP6 — user deck persistence over data/userdecks.sqlite (read-WRITE).

This module owns the ONLY writable DB in the app. `Store` stays read-only.
One connection, opened in `UserDecks.__init__` with check_same_thread=False,
WAL + foreign_keys ON; a threading.Lock guards writes (FastAPI sync endpoints
run in a threadpool). Saving cards is a FULL REPLACE inside one transaction.
All methods return plain dicts; pydantic validation happens in the routers.
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from . import config


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
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ---- reads -----------------------------------------------------------
    def list_decks(self) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT d.id, d.name, d.commander_id, d.updated_at,
                   COALESCE(SUM(c.quantity), 0) AS card_count
            FROM decks d
            LEFT JOIN deck_cards c ON c.deck_id = d.id
            GROUP BY d.id
            ORDER BY d.updated_at DESC
            """
        ).fetchall()
        return [
            {"id": r[0], "name": r[1], "commander_id": r[2],
             "updated_at": r[3], "card_count": int(r[4])}
            for r in rows
        ]

    def get(self, deck_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT id, name, commander_id, created_at, updated_at FROM decks WHERE id=?",
            (deck_id,),
        ).fetchone()
        if row is None:
            return None
        cards = self._conn.execute(
            "SELECT card_id, zone, quantity FROM deck_cards WHERE deck_id=?",
            (deck_id,),
        ).fetchall()
        return {
            "id": row[0], "name": row[1], "commander_id": row[2],
            "created_at": row[3], "updated_at": row[4],
            "cards": [{"card_id": c[0], "zone": c[1], "quantity": c[2]} for c in cards],
        }

    # ---- writes ----------------------------------------------------------
    def _write_cards(self, deck_id: str, cards: list[dict]) -> None:
        """Replace deck_cards for one deck. Caller holds the lock + a txn."""
        self._conn.execute("DELETE FROM deck_cards WHERE deck_id=?", (deck_id,))
        self._conn.executemany(
            "INSERT INTO deck_cards (deck_id, card_id, zone, quantity) VALUES (?,?,?,?)",
            [(deck_id, c.get("id") or c["card_id"], c.get("zone", "Utility"),
              int(c.get("quantity", 1))) for c in cards],
        )

    def create(self, name: str, commander_id: str | None, cards: list[dict]) -> str:
        deck_id = uuid.uuid4().hex
        ts = _now()
        with self._lock:
            self._conn.execute(
                "INSERT INTO decks (id, name, commander_id, created_at, updated_at) "
                "VALUES (?,?,?,?,?)",
                (deck_id, name, commander_id, ts, ts),
            )
            self._write_cards(deck_id, cards)
            self._conn.commit()
        return deck_id

    def update(self, deck_id: str, name: str, commander_id: str | None,
               cards: list[dict]) -> bool:
        with self._lock:
            exists = self._conn.execute(
                "SELECT 1 FROM decks WHERE id=?", (deck_id,)).fetchone()
            if exists is None:
                return False
            self._conn.execute(
                "UPDATE decks SET name=?, commander_id=?, updated_at=? WHERE id=?",
                (name, commander_id, _now(), deck_id),
            )
            self._write_cards(deck_id, cards)
            self._conn.commit()
        return True

    def delete(self, deck_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM decks WHERE id=?", (deck_id,))
            self._conn.commit()
        return cur.rowcount > 0


@lru_cache(maxsize=1)
def get_userdecks() -> UserDecks:
    return UserDecks(config.USERDECKS_PATH)
