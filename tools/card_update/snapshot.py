"""Read card files and SQLite stores into the plain inputs the gates judge."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from card_update.gates import StoreSnapshot


def load_json_file(path: Path) -> tuple[Any, str | None]:
    """(data, None) or (None, error) — parse failures are gate input, not exceptions."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh), None
    except (OSError, ValueError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


def load_cards(path: Path) -> list[dict]:
    data, err = load_json_file(path)
    if err is not None:
        raise ValueError(f"cannot read cards file {path}: {err}")
    cards = data["data"] if isinstance(data, dict) and "data" in data else data
    if not isinstance(cards, list):
        raise ValueError(f"cards file {path} is not a JSON array")
    return cards


def _connect_ro(path: Path) -> sqlite3.Connection:
    if not Path(path).exists():
        raise FileNotFoundError(f"store not found: {path}")
    return sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True)


def _has_tags(raw: Any) -> bool:
    if not raw:
        return False
    try:
        return bool(json.loads(raw))
    except (TypeError, ValueError):
        return False


def read_store(path: Path, check_integrity: bool) -> StoreSnapshot:
    con = _connect_ro(path)
    try:
        integrity = ""
        if check_integrity:
            rows = [r[0] for r in con.execute("PRAGMA integrity_check")]
            integrity = "ok" if rows == ["ok"] else "; ".join(str(r) for r in rows[:10])
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        counts = {t: con.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0] for t in tables}
        ier: dict[str, float | None] = {}
        if "cards" in tables:
            ier = {cid: v for cid, v in con.execute("SELECT id, ier FROM cards")}
        tagged: set[str] = set()
        if "card_flat_tags" in tables:
            tagged = {cid for cid, tags in con.execute("SELECT card_id, tags FROM card_flat_tags")
                      if _has_tags(tags)}
        return StoreSnapshot(integrity=integrity, table_counts=counts, card_ids=frozenset(ier),
                             tagged_ids=frozenset(tagged), ier=ier)
    finally:
        con.close()


def finalize_sqlite(path: Path) -> None:
    """Checkpoint WAL and switch to rollback-journal mode so the file is self-contained
    (safe to move, copy or hash without -wal/-shm sidecars)."""
    con = sqlite3.connect(str(path))
    try:
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        mode = con.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
        if str(mode).lower() != "delete":
            raise RuntimeError(f"{path}: could not leave WAL mode (journal_mode={mode})")
    finally:
        con.close()
    for suffix in ("-wal", "-shm"):
        side = Path(str(path) + suffix)
        if side.exists():
            if side.stat().st_size and suffix == "-wal":
                raise RuntimeError(f"{side} still holds un-checkpointed data")
            side.unlink()
