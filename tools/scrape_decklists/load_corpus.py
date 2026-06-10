"""Load the scraped JSONL corpus into two SQLite databases.

The scraper (runner.py) emits durable, append-only, parallel-safe JSON-lines.
This step folds all of it into the two query-ready databases the SP3 mining
package reads:

  data/decks.sqlite     decks(deck_id, source, commander)
                        deck_cards(deck_id, card_name)        -- normalized presence
  data/edhrec.sqlite    edhrec_metrics(commander, card_name, synergy, inclusion)

Idempotent and re-runnable: run it any time (including while a scrape is in
progress) to refresh the DBs from the current corpus. Computes NO statistics —
it only transcribes raw records; lift/synergy fusion lives in scoring/cooccurrence/.

Usage:
    python tools/scrape_decklists/load_corpus.py
    python tools/scrape_decklists/load_corpus.py --corpus data/decklists --out data
"""

from __future__ import annotations

import argparse
import glob
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _connect(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    return con


def _init_decks(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS decks (
            deck_id   TEXT PRIMARY KEY,
            source    TEXT NOT NULL,
            commander TEXT
        );
        CREATE TABLE IF NOT EXISTS deck_cards (
            deck_id   TEXT NOT NULL,
            card_name TEXT NOT NULL,
            PRIMARY KEY (deck_id, card_name)
        );
        CREATE INDEX IF NOT EXISTS idx_deck_cards_card ON deck_cards(card_name);
        """
    )


def _init_edhrec(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS edhrec_metrics (
            commander TEXT NOT NULL,
            card_name TEXT NOT NULL,
            synergy   REAL,
            inclusion REAL,
            PRIMARY KEY (commander, card_name)
        );
        CREATE INDEX IF NOT EXISTS idx_edhrec_commander ON edhrec_metrics(commander);
        """
    )


def load(corpus_dir: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    decks_con = _connect(out_dir / "decks.sqlite")
    edhrec_con = _connect(out_dir / "edhrec.sqlite")
    _init_decks(decks_con)
    _init_edhrec(edhrec_con)

    n_decks = n_cards = n_edhrec_rows = n_edhrec_cmdrs = skipped = 0
    files = sorted(glob.glob(str(corpus_dir / "*.jsonl")))
    for fp in files:
        with open(fp, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    skipped += 1
                    continue
                kind = rec.get("kind")
                if kind == "deck":
                    deck_id = rec.get("deck_id")
                    names = rec.get("card_names") or []
                    if not deck_id or not names:
                        skipped += 1
                        continue
                    decks_con.execute(
                        "INSERT OR REPLACE INTO decks (deck_id, source, commander) VALUES (?,?,?)",
                        (deck_id, rec.get("source", ""), rec.get("commander")),
                    )
                    # dedup card presence within a deck via PK(deck_id, card_name)
                    decks_con.executemany(
                        "INSERT OR IGNORE INTO deck_cards (deck_id, card_name) VALUES (?,?)",
                        [(deck_id, name) for name in dict.fromkeys(names)],
                    )
                    n_decks += 1
                    n_cards += len(set(names))
                elif kind == "edhrec":
                    commander = rec.get("commander")
                    cards = rec.get("cards") or []
                    if not commander or not cards:
                        skipped += 1
                        continue
                    edhrec_con.executemany(
                        "INSERT OR REPLACE INTO edhrec_metrics "
                        "(commander, card_name, synergy, inclusion) VALUES (?,?,?,?)",
                        [(commander, c.get("name"), c.get("synergy"), c.get("inclusion"))
                         for c in cards if c.get("name")],
                    )
                    n_edhrec_rows += sum(1 for c in cards if c.get("name"))
                    n_edhrec_cmdrs += 1
                else:
                    skipped += 1

    decks_con.commit()
    edhrec_con.commit()
    # de-duplicated totals from the DB (the corpus may carry repeat deck_ids
    # across batches; INSERT OR REPLACE collapses them)
    uniq_decks = decks_con.execute("SELECT COUNT(*) FROM decks").fetchone()[0]
    uniq_cmdrs = edhrec_con.execute(
        "SELECT COUNT(DISTINCT commander) FROM edhrec_metrics").fetchone()[0]
    decks_con.close()
    edhrec_con.close()
    return {
        "files": len(files),
        "deck_records_read": n_decks, "unique_decks": uniq_decks,
        "edhrec_records_read": n_edhrec_cmdrs, "unique_commanders": uniq_cmdrs,
        "edhrec_metric_rows": n_edhrec_rows, "skipped": skipped,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Load JSONL corpus into decks.sqlite + edhrec.sqlite")
    ap.add_argument("--corpus", default=str(ROOT / "data" / "decklists"))
    ap.add_argument("--out", default=str(ROOT / "data"))
    args = ap.parse_args()
    stats = load(Path(args.corpus), Path(args.out))
    print(f"decks.sqlite:  {stats['unique_decks']:,} unique decks "
          f"({stats['deck_records_read']:,} records read)")
    print(f"edhrec.sqlite: {stats['unique_commanders']:,} commanders, "
          f"{stats['edhrec_metric_rows']:,} metric rows")
    print(f"files: {stats['files']}  |  skipped lines: {stats['skipped']:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
