"""Build the co-occurrence layer and fuse it into SP1's synergy.

Order matters: run AFTER build_relationships.py (which DROPs+recreates
card_relationships). This reads the freshly-built structural synergy_ab/ba,
snapshots them to structural_synergy_ab/ba, writes card_cooccurrence, then
overwrites synergy_ab/ba with fuse(structural, lift_norm, edhrec). Re-running
build_relationships resets to structural; re-run this to re-fuse.

Usage:
    python scoring/build_cooccurrence.py --scores data/scores.sqlite \
        --decks data/decks.sqlite --edhrec data/edhrec.sqlite --min-support 20
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cooccurrence.corpus import (  # noqa: E402
    name_to_id_map, decks_from_db, decks_from_jsonl,
    edhrec_from_db, edhrec_from_jsonl,
)
from cooccurrence.mine import mine_pairs  # noqa: E402
from cooccurrence.edhrec import directional_synergy  # noqa: E402
from cooccurrence.fuse import lift_to_norm, fuse  # noqa: E402


def build(scores_db: str, decks_source: str, edhrec_source: str,
          min_support: int = 20, from_jsonl: bool = False) -> dict:
    name_to_id = name_to_id_map(scores_db)
    if from_jsonl:
        decks = decks_from_jsonl(decks_source, name_to_id)
        edh_rows = edhrec_from_jsonl(edhrec_source, name_to_id)
    else:
        decks = decks_from_db(decks_source, name_to_id)
        edh_rows = edhrec_from_db(edhrec_source, name_to_id)

    pairs = mine_pairs(decks, min_support=min_support)
    edh = directional_synergy(edh_rows)

    con = sqlite3.connect(scores_db)
    con.executescript("""
        DROP TABLE IF EXISTS card_cooccurrence;
        CREATE TABLE card_cooccurrence (
            a TEXT, b TEXT, co_count INT, lift REAL, jaccard REAL, support INT,
            edhrec_synergy_ab REAL, edhrec_synergy_ba REAL, PRIMARY KEY (a, b));
        CREATE INDEX idx_cooc_a ON card_cooccurrence(a, lift DESC);
    """)
    rows = []
    for (a, b), m in sorted(pairs.items()):
        rows.append((a, b, m["co_count"], m["lift"], m["jaccard"], m["support"],
                     edh.get((a, b), 0.0), edh.get((b, a), 0.0)))
    con.executemany("INSERT OR REPLACE INTO card_cooccurrence VALUES (?,?,?,?,?,?,?,?)", rows)

    cols = [r[1] for r in con.execute("PRAGMA table_info(card_relationships)")]
    if "structural_synergy_ab" not in cols:
        con.execute("ALTER TABLE card_relationships ADD COLUMN structural_synergy_ab REAL")
        con.execute("ALTER TABLE card_relationships ADD COLUMN structural_synergy_ba REAL")
        con.execute("UPDATE card_relationships SET structural_synergy_ab=synergy_ab, "
                    "structural_synergy_ba=synergy_ba WHERE structural_synergy_ab IS NULL")

    lift_norm = {k: lift_to_norm(m["lift"]) for k, m in pairs.items()}
    fused = 0
    for a, b, s_ab, s_ba in con.execute(
            "SELECT a, b, structural_synergy_ab, structural_synergy_ba "
            "FROM card_relationships").fetchall():
        ln = lift_norm.get((a, b), 0.0)
        new_ab = fuse(s_ab or 0.0, ln, edh.get((a, b), 0.0))
        new_ba = fuse(s_ba or 0.0, ln, edh.get((b, a), 0.0))
        con.execute("UPDATE card_relationships SET synergy_ab=?, synergy_ba=? WHERE a=? AND b=?",
                    (new_ab, new_ba, a, b))
        fused += 1
    con.commit(); con.close()
    return {"pairs": len(rows), "edhrec_pairs": len(edh), "refused_rows": fused,
            "decks": len(decks)}


def main() -> None:
    p = argparse.ArgumentParser(description="Build card_cooccurrence + fuse SP1 synergy.")
    p.add_argument("--scores", default="data/scores.sqlite")
    p.add_argument("--decks", default="data/decks.sqlite")
    p.add_argument("--edhrec", default="data/edhrec.sqlite")
    p.add_argument("--min-support", type=int, default=20)
    a = p.parse_args()
    stats = build(a.scores, a.decks, a.edhrec, min_support=a.min_support)
    print(f"cooccurrence: {stats['pairs']:,} pairs | edhrec dir-pairs: {stats['edhrec_pairs']:,} "
          f"| re-fused rows: {stats['refused_rows']:,} | decks: {stats['decks']:,}")


if __name__ == "__main__":
    main()
