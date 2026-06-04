"""Card + score store.

Loads card metadata (sample JSON now, simmander DB later) into memory for O(1)
lookups and opens the generated SQLite synergy store read-only. All public
methods are pure lookups — no scoring happens at request time.
"""

from __future__ import annotations

import json
import sqlite3
from functools import lru_cache
from pathlib import Path

from . import config


class Store:
    def __init__(self, cards_path: Path, scores_path: Path):
        self._cards: dict[str, dict] = {}
        self._ier: dict[str, float] = {}
        self._tags: dict[str, list[str]] = {}
        self.scores_path = scores_path
        self._load_cards(cards_path)
        self._load_score_enrichment(scores_path)

    def _load_cards(self, path: Path) -> None:
        if not path.exists():
            return
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        cards = data["data"] if isinstance(data, dict) and "data" in data else data
        for c in cards:
            self._cards[c["id"]] = c

    def _load_score_enrichment(self, path: Path) -> None:
        if not path.exists():
            return
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        for cid, ier, tags in conn.execute("SELECT id, ier, mechanic_tags FROM cards"):
            self._ier[cid] = ier
            self._tags[cid] = json.loads(tags or "[]")
        conn.close()

    # ---- card access -----------------------------------------------------
    def get(self, card_id: str) -> dict | None:
        card = self._cards.get(card_id)
        if card is None:
            return None
        enriched = dict(card)
        enriched["ier"] = self._ier.get(card_id)
        enriched["mechanic_tags"] = self._tags.get(card_id, [])
        return enriched

    def search(self, q: str = "", colors: str = "", type_q: str = "",
               max_cmc: float | None = None, limit: int = 60) -> list[dict]:
        q = q.lower().strip()
        color_set = {c.upper() for c in colors if c.strip()}
        type_q = type_q.lower().strip()
        out: list[dict] = []
        for cid, card in self._cards.items():
            if q and q not in card.get("name", "").lower():
                continue
            if type_q and type_q not in card.get("type_line", "").lower():
                continue
            if max_cmc is not None and (card.get("cmc") or 0) > max_cmc:
                continue
            if color_set and not color_set.issubset(set(card.get("color_identity") or [])):
                continue
            out.append(self.get(cid))  # type: ignore[arg-type]
            if len(out) >= limit:
                break
        return out

    def ier(self, card_id: str) -> float | None:
        return self._ier.get(card_id)

    # ---- synergy access (O(1) indexed reads) -----------------------------
    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(f"file:{self.scores_path}?mode=ro", uri=True)

    def pair(self, a: str, b: str) -> dict | None:
        if not self.scores_path.exists():
            return None
        key = tuple(sorted((a, b)))
        conn = self._conn()
        row = conn.execute(
            "SELECT card_a, card_b, css, der, lift FROM synergies "
            "WHERE card_a=? AND card_b=?",
            key,
        ).fetchone()
        conn.close()
        if not row:
            return None
        return {"card_a": row[0], "card_b": row[1], "css": row[2],
                "der": row[3], "lift": bool(row[4])}

    def neighbours(self, card_id: str, limit: int = 12) -> list[dict]:
        if not self.scores_path.exists():
            return []
        conn = self._conn()
        rows = conn.execute(
            "SELECT card_a, card_b, css, der, lift FROM synergies "
            "WHERE card_a=? OR card_b=? ORDER BY der DESC LIMIT ?",
            (card_id, card_id, limit),
        ).fetchall()
        conn.close()
        return [{"card_a": r[0], "card_b": r[1], "css": r[2],
                 "der": r[3], "lift": bool(r[4])} for r in rows]

    def synergies_among(self, ids: list[str], limit: int = 20) -> list[dict]:
        """Top synergy edges whose both endpoints are in the deck."""
        idset = set(ids)
        edges: list[dict] = []
        for cid in ids:
            for edge in self.neighbours(cid, limit=50):
                other = edge["card_b"] if edge["card_a"] == cid else edge["card_a"]
                if other in idset:
                    edges.append(edge)
        # dedupe by sorted pair
        seen = set()
        uniq = []
        for e in sorted(edges, key=lambda x: x["der"], reverse=True):
            k = tuple(sorted((e["card_a"], e["card_b"])))
            if k in seen:
                continue
            seen.add(k)
            uniq.append(e)
        return uniq[:limit]


@lru_cache(maxsize=1)
def get_store() -> Store:
    return Store(config.CARDS_PATH, config.SCORES_PATH)
