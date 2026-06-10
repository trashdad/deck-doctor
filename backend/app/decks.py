"""SP6 — user deck persistence over data/userdecks.sqlite (read-WRITE).

SCAFFOLD — implement per docs/superpowers/plans/2026-06-10-sp6-sp11-roadmap.md §6.1–6.2.

Design constraints (binding):
- This module owns the ONLY writable DB in the app. `Store` stays read-only.
- One connection, opened in `UserDecks.__init__` with `check_same_thread=False`,
  `PRAGMA journal_mode=WAL`, `PRAGMA foreign_keys=ON`; a `threading.Lock` guards writes.
- Schema (create on init if absent):
    decks(id TEXT PK uuid4().hex, name TEXT NOT NULL, commander_id TEXT,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL)        -- UTC isoformat
    deck_cards(deck_id TEXT NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
               card_id TEXT NOT NULL, zone TEXT NOT NULL DEFAULT 'Utility',
               quantity INTEGER NOT NULL DEFAULT 1, PRIMARY KEY (deck_id, card_id))
- Saving cards is a FULL REPLACE inside one transaction (DELETE then executemany INSERT).
- All methods return plain dicts; pydantic validation happens in the routers.
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from . import config


class UserDecks:
    def __init__(self, path: Path):
        self.path = path
        # TODO(SP6): open connection, pragmas, create tables (roadmap §6.1)
        raise NotImplementedError("SP6 pending — roadmap §6.1")

    def list_decks(self) -> list[dict]:
        """[{id, name, commander_id, card_count, updated_at}] ORDER BY updated_at DESC.

        card_count = SUM(quantity) per deck (LEFT JOIN so empty decks count 0).
        """
        raise NotImplementedError("SP6 pending — roadmap §6.1")

    def create(self, name: str, commander_id: str | None, cards: list[dict]) -> str:
        """Insert deck + cards; return the new id (uuid4().hex).

        `cards` rows: {"id": card_id, "zone": str, "quantity": int} (DeckEntry shape).
        """
        raise NotImplementedError("SP6 pending — roadmap §6.1")

    def get(self, deck_id: str) -> dict | None:
        """{id, name, commander_id, created_at, updated_at,
            cards: [{card_id, zone, quantity}]} or None."""
        raise NotImplementedError("SP6 pending — roadmap §6.1")

    def update(self, deck_id: str, name: str, commander_id: str | None,
               cards: list[dict]) -> bool:
        """Full replace of name/commander/cards; bump updated_at. False if deck missing."""
        raise NotImplementedError("SP6 pending — roadmap §6.1")

    def delete(self, deck_id: str) -> bool:
        """Delete deck (cascade removes cards). False if deck missing."""
        raise NotImplementedError("SP6 pending — roadmap §6.1")


@lru_cache(maxsize=1)
def get_userdecks() -> UserDecks:
    return UserDecks(config.USERDECKS_PATH)
