"""SP7 load — data/spellbook_raw.jsonl -> data/spellbook.sqlite.

stdlib-only. Drops + recreates both tables (idempotent rebuild). Keep a variant iff
status == "OK" AND legalities["commander"] is True AND not spoiler AND 2 <= len(uses) <= 6.

CLI: python tools/import_spellbook/load_spellbook.py [--raw PATH] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_PATH = ROOT / "data" / "spellbook_raw.jsonl"
OUT_PATH = ROOT / "data" / "spellbook.sqlite"

_SCHEMA = """
DROP TABLE IF EXISTS combos;
DROP TABLE IF EXISTS combo_cards;
CREATE TABLE combos (
    combo_id    TEXT PRIMARY KEY,
    identity    TEXT,
    popularity  INTEGER,
    bracket_tag TEXT,
    description TEXT,
    mana_needed TEXT,
    easy_prereq TEXT,
    notable_prereq TEXT,
    produces    TEXT NOT NULL,
    card_count  INTEGER NOT NULL
);
CREATE TABLE combo_cards (
    combo_id  TEXT NOT NULL,
    card_name TEXT NOT NULL,
    quantity  INTEGER NOT NULL DEFAULT 1,
    must_be_commander INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (combo_id, card_name)
);
CREATE INDEX idx_combo_cards_name ON combo_cards(card_name);
"""


def _keep(v: dict) -> bool:
    uses = v.get("uses") or []
    legal = (v.get("legalities") or {}).get("commander") is True
    return (v.get("status") == "OK" and legal and not v.get("spoiler", False)
            and 2 <= len(uses) <= 6)


def load(raw_path: Path, out_path: Path) -> dict:
    con = sqlite3.connect(out_path)
    con.executescript(_SCHEMA)
    read = kept = skipped = 0
    with raw_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            read += 1
            try:
                v = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue
            if not _keep(v):
                skipped += 1
                continue
            combo_id = str(v["id"])
            uses = v["uses"]
            produces = [p["feature"]["name"] for p in (v.get("produces") or [])
                        if p.get("feature")]
            con.execute(
                "INSERT OR REPLACE INTO combos (combo_id, identity, popularity, bracket_tag, "
                "description, mana_needed, easy_prereq, notable_prereq, produces, card_count) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (combo_id, v.get("identity", ""), v.get("popularity"),
                 v.get("bracketTag", ""), v.get("description", ""), v.get("manaNeeded", ""),
                 v.get("easyPrerequisites", ""), v.get("notablePrerequisites", ""),
                 json.dumps(produces), len(uses)),
            )
            rows = []
            for u in uses:
                card = u.get("card") or {}
                name = card.get("name")
                if not name:
                    continue
                rows.append((combo_id, name, int(u.get("quantity", 1)),
                             1 if u.get("mustBeCommander") else 0))
            con.executemany(
                "INSERT OR IGNORE INTO combo_cards (combo_id, card_name, quantity, "
                "must_be_commander) VALUES (?,?,?,?)", rows)
            kept += 1
    con.commit()
    con.close()
    return {"read": read, "kept": kept, "skipped": skipped}


def main() -> int:
    ap = argparse.ArgumentParser(description="Load spellbook_raw.jsonl into spellbook.sqlite")
    ap.add_argument("--raw", default=str(RAW_PATH))
    ap.add_argument("--out", default=str(OUT_PATH))
    args = ap.parse_args()
    stats = load(Path(args.raw), Path(args.out))
    print(f"spellbook: read {stats['read']:,} variants, kept {stats['kept']:,}, "
          f"skipped {stats['skipped']:,} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
