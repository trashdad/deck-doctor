"""Orchestrate the card-fingerprint build: project -> persist -> derive -> QA.

Usage:
    python scoring/build_fingerprints.py \
        --mtgish C:/simmander/simmander/mtgish/data/cards.json \
        --cards  data/cards.json \
        --db     data/scores.sqlite
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_semantics import norm_name  # noqa: E402  (reuse the proven name join)
from fingerprints.project import project_card  # noqa: E402
from fingerprints.schema import AbilityRecord  # noqa: E402
from fingerprints.derive import (  # noqa: E402
    flat_tags, ability_tag_lists, build_inverted_index,
)
from fingerprints.qa import coverage_report, unmapped_operators  # noqa: E402


def _load_outliers(outliers_dir: str) -> dict[str, list[AbilityRecord]]:
    """data/outliers/*.json -> {card_id: [AbilityRecord,...]}.

    Each file: {"card_id": "...", "records": [<record dict>, ...]}.
    """
    out: dict[str, list[AbilityRecord]] = {}
    d = Path(outliers_dir)
    if not d.is_dir():
        return out
    for f in sorted(d.glob("*.json")):
        obj = json.loads(f.read_text(encoding="utf-8"))
        out[obj["card_id"]] = [AbilityRecord.from_dict(r) for r in obj["records"]]
    return out


def build(mtgish_path: str, cards_path: str, db_path: str,
          outliers_dir: str = "data/outliers") -> dict:
    mtgish = json.loads(Path(mtgish_path).read_text(encoding="utf-8"))
    raw = json.loads(Path(cards_path).read_text(encoding="utf-8"))
    cards = raw["data"] if isinstance(raw, dict) and "data" in raw else raw

    name_to_id = {norm_name(c["name"]): c["id"] for c in cards}
    outliers = _load_outliers(outliers_dir)

    fingerprints: dict[str, list[AbilityRecord]] = {}
    matched = 0
    for mc in mtgish:
        cid = name_to_id.get(norm_name(mc.get("Name", "")))
        if cid is None:
            continue
        fingerprints[cid] = project_card(mc)
        matched += 1
    fingerprints.update(outliers)  # hand-coded outliers win

    # Derive views
    per_card_tags = {cid: flat_tags(recs) for cid, recs in fingerprints.items()}

    con = sqlite3.connect(db_path)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript("""
        DROP TABLE IF EXISTS card_fingerprints;
        CREATE TABLE card_fingerprints (
            card_id TEXT NOT NULL, ability_idx INTEGER NOT NULL,
            record TEXT NOT NULL, source TEXT, confidence REAL,
            PRIMARY KEY (card_id, ability_idx));
        DROP TABLE IF EXISTS card_fingerprint_flat;
        CREATE TABLE card_fingerprint_flat (
            card_id TEXT PRIMARY KEY, record TEXT NOT NULL);
        DROP TABLE IF EXISTS card_ability_tags;
        CREATE TABLE card_ability_tags (
            card_id TEXT NOT NULL, ability_idx INTEGER NOT NULL,
            tags TEXT NOT NULL DEFAULT '[]', PRIMARY KEY (card_id, ability_idx));
        DROP TABLE IF EXISTS card_flat_tags;
        CREATE TABLE card_flat_tags (card_id TEXT PRIMARY KEY, tags TEXT NOT NULL DEFAULT '[]');
        DROP TABLE IF EXISTS tag_inverted_index;
        CREATE TABLE tag_inverted_index (tag TEXT PRIMARY KEY, card_ids TEXT NOT NULL DEFAULT '[]');
    """)

    for cid, recs in fingerprints.items():
        source = "outlier" if cid in outliers else "mtgish"
        for rec in recs:
            con.execute("INSERT OR REPLACE INTO card_fingerprints VALUES (?,?,?,?,?)",
                        (cid, rec.ability_idx, json.dumps(rec.to_dict()), source, 1.0))
        con.execute("INSERT OR REPLACE INTO card_fingerprint_flat VALUES (?,?)",
                    (cid, json.dumps([r.to_dict() for r in recs])))
        for idx, tags in enumerate(ability_tag_lists(recs)):
            con.execute("INSERT OR REPLACE INTO card_ability_tags VALUES (?,?,?)",
                        (cid, idx, json.dumps(tags)))
        con.execute("INSERT OR REPLACE INTO card_flat_tags VALUES (?,?)",
                    (cid, json.dumps(per_card_tags[cid])))

    inv = build_inverted_index(per_card_tags)
    con.executemany("INSERT INTO tag_inverted_index VALUES (?,?)",
                    [(t, json.dumps(ids)) for t, ids in inv.items()])
    con.commit()
    con.close()

    cov = coverage_report(per_card_tags, total_cards=len(cards))
    unmapped = unmapped_operators(mtgish)
    return {"matched": matched, "coverage": cov, "unmapped_top": unmapped[:25]}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--mtgish", default="C:/simmander/simmander/mtgish/data/cards.json")
    p.add_argument("--cards", default="data/cards.json")
    p.add_argument("--db", default="data/scores.sqlite")
    p.add_argument("--outliers", default="data/outliers")
    a = p.parse_args()
    stats = build(a.mtgish, a.cards, a.db, outliers_dir=a.outliers)
    print(f"Matched {stats['matched']:,} cards")
    print(f"Coverage: {stats['coverage']}")
    print("Top unmapped operators (occurrence-weighted):")
    for op, n in stats["unmapped_top"]:
        print(f"  {n:>6}  {op}")


if __name__ == "__main__":
    main()
