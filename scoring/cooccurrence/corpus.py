"""Load the acquisition corpus into id-resolved structures for mining.

Reads either the built databases (data/decks.sqlite + data/edhrec.sqlite) or the
committed sample JSONL. Card names are resolved to ids via the SP2 `cards` table
join; unresolved names are dropped (they cannot be scored). Computes no stats.
"""

from __future__ import annotations

import json
import sqlite3
import unicodedata
from collections import defaultdict
from pathlib import Path


def norm(name: str) -> str:
    """Accent/case-folded card-name key (identical to relationships.combo._norm)."""
    nfkd = unicodedata.normalize("NFKD", name or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def name_to_id_map(scores_db_path: str) -> dict:
    """norm(card name) -> card id, from the SP2 `cards` table."""
    con = sqlite3.connect(f"file:{scores_db_path}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT id, name FROM cards").fetchall()
    finally:
        con.close()
    return {norm(name): cid for cid, name in rows}


def _resolve(names, name_to_id) -> frozenset:
    out = set()
    for n in names:
        cid = name_to_id.get(norm(n))
        if cid is not None:
            out.add(cid)
    return frozenset(out)


def decks_from_db(decks_db_path: str, name_to_id: dict) -> list:
    """Each deck -> frozenset of card ids (unknown names dropped)."""
    con = sqlite3.connect(f"file:{decks_db_path}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT deck_id, card_name FROM deck_cards ORDER BY deck_id").fetchall()
    finally:
        con.close()
    by_deck: dict = defaultdict(list)
    for deck_id, name in rows:
        by_deck[deck_id].append(name)
    return [d for d in (_resolve(names, name_to_id) for names in by_deck.values()) if d]


def decks_from_jsonl(path, name_to_id: dict) -> list:
    """Same as decks_from_db but from a JSONL corpus file (sample fixture)."""
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        if rec.get("kind") != "deck":
            continue
        ids = _resolve(rec.get("card_names") or [], name_to_id)
        if ids:
            out.append(ids)
    return out


def edhrec_from_db(edhrec_db_path: str, name_to_id: dict) -> list:
    """(commander_id, card_id, synergy) directional rows; unknowns dropped."""
    con = sqlite3.connect(f"file:{edhrec_db_path}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT commander, card_name, synergy FROM edhrec_metrics").fetchall()
    finally:
        con.close()
    out = []
    for commander, card_name, synergy in rows:
        cid = name_to_id.get(norm(commander))
        bid = name_to_id.get(norm(card_name))
        if cid is not None and bid is not None and synergy is not None:
            out.append((cid, bid, float(synergy)))
    return out


def edhrec_from_jsonl(path, name_to_id: dict) -> list:
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        if rec.get("kind") != "edhrec":
            continue
        cid = name_to_id.get(norm(rec.get("commander", "")))
        if cid is None:
            continue
        for c in rec.get("cards") or []:
            bid = name_to_id.get(norm(c.get("name", "")))
            if bid is not None and c.get("synergy") is not None:
                out.append((cid, bid, float(c["synergy"])))
    return out
