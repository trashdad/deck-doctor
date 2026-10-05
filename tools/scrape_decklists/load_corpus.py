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

Decks whose card names are JSON field names, or that have fewer than 2
names resolving against the cards table, are rejected and counted. An
accepted deck replaces that deck's card rows so a later good parse does
not keep an earlier shell. A field-name record also deletes stored
field-name rows for its deck (never real cards), and the deck itself if
no cards remain, so reloading the corpus cleans shells already stored.

Usage:
    python tools/scrape_decklists/load_corpus.py
    python tools/scrape_decklists/load_corpus.py --corpus data/decklists --out data
"""

from __future__ import annotations

import argparse
import glob
import json
import sqlite3
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# JSON object keys the deckpreview parser used to store as card names.
# None of these are printed Magic card names (checked against the cards table).
FIELD_NAME_CARDS = frozenset({"cards", "commander", "commander_v2"})
# Junk guard, not a deck-size policy: a commander plus at least one other
# real card. "Any number of copies" decks (Relentless Rats, Rat Colony, ...)
# store as few as 2 distinct names. Deck-size filtering belongs in scoring.
MIN_RESOLVABLE_CARDS = 2


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


def _norm(name: str) -> str:
    """Accent/case-folded key. Same fold as scoring/cooccurrence/corpus.py:norm."""
    nfkd = unicodedata.normalize("NFKD", name or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def _resolvable_names(scores_db: Path | None) -> set[str] | None:
    """norm(card name) set from the SP2 cards table, or None if it cannot be read."""
    if scores_db is None or not scores_db.exists():
        return None
    try:
        con = sqlite3.connect(f"file:{scores_db.as_posix()}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        rows = con.execute("SELECT name FROM cards").fetchall()
    except sqlite3.Error:
        return None
    finally:
        con.close()
    return {_norm(r[0]) for r in rows if r and r[0]}


def _clean_names(names) -> list[str]:
    if not isinstance(names, list):
        return []
    out: list[str] = []
    for n in names:
        if isinstance(n, str) and n.strip():
            out.append(n.strip())
    return list(dict.fromkeys(out))


def deck_rejection(names, resolvable: set[str] | None) -> str | None:
    """Why this deck must not be stored, or None if it is safe to load.

    Rejects a card_names dict (its keys are field names), any list that
    contains the field-name tokens, and any list with fewer than
    MIN_RESOLVABLE_CARDS names that resolve in `resolvable`. When the card
    table is unavailable, the size check uses distinct raw names so a
    3-token shell is still rejected.
    """
    if isinstance(names, dict):
        return "field_names"
    cleaned = _clean_names(names)
    if not cleaned:
        return "empty"
    if {n.casefold() for n in cleaned} & FIELD_NAME_CARDS:
        return "field_names"
    if resolvable is None:
        n_res = len(cleaned)
    else:
        n_res = len({n for n in cleaned if _norm(n) in resolvable})
    if n_res < MIN_RESOLVABLE_CARDS:
        return "too_few_resolvable"
    return None


def load(corpus_dir: Path, out_dir: Path, scores_db: Path | None = None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    decks_con = _connect(out_dir / "decks.sqlite")
    edhrec_con = _connect(out_dir / "edhrec.sqlite")
    _init_decks(decks_con)
    _init_edhrec(edhrec_con)

    if scores_db is None:
        scores_db = ROOT / "data" / "scores.sqlite"
    resolvable = _resolvable_names(scores_db)
    if resolvable is None:
        print("resolver: cards table unavailable; "
              "too-few guard counts distinct names")
    else:
        print(f"resolver: {len(resolvable):,} card names")

    n_decks = n_cards = n_edhrec_rows = n_edhrec_cmdrs = skipped = 0
    rejected = n_field = n_few = 0
    purged_decks = purged_rows = 0
    field_marks = ",".join("?" * len(FIELD_NAME_CARDS))
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
                    raw_names = rec.get("card_names")
                    if not deck_id or raw_names is None:
                        skipped += 1
                        continue
                    reason = deck_rejection(raw_names, resolvable)
                    if reason == "empty":
                        skipped += 1
                        continue
                    if reason:
                        rejected += 1
                        if reason == "field_names":
                            n_field += 1
                            # Clean a shell stored by the pre-fix loader: drop
                            # only field-name rows, then the deck if it is empty.
                            purged_rows += decks_con.execute(
                                f"DELETE FROM deck_cards WHERE deck_id = ? "
                                f"AND lower(card_name) IN ({field_marks})",
                                (deck_id, *sorted(FIELD_NAME_CARDS)),
                            ).rowcount
                            purged_decks += decks_con.execute(
                                "DELETE FROM decks WHERE deck_id = ? AND NOT EXISTS "
                                "(SELECT 1 FROM deck_cards WHERE deck_id = ?)",
                                (deck_id, deck_id),
                            ).rowcount
                        else:
                            n_few += 1
                        continue
                    names = _clean_names(raw_names)
                    decks_con.execute(
                        "INSERT OR REPLACE INTO decks (deck_id, source, commander) VALUES (?,?,?)",
                        (deck_id, rec.get("source", ""), rec.get("commander")),
                    )
                    # Replace the card set. INSERT OR IGNORE alone kept field-name
                    # rows forever after a later good parse (and the reverse).
                    decks_con.execute("DELETE FROM deck_cards WHERE deck_id = ?", (deck_id,))
                    decks_con.executemany(
                        "INSERT OR IGNORE INTO deck_cards (deck_id, card_name) VALUES (?,?)",
                        [(deck_id, name) for name in names],
                    )
                    n_decks += 1
                    n_cards += len(names)
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
    print(f"rejected decks: {rejected:,} "
          f"(field_names={n_field:,}, too_few_resolvable={n_few:,})")
    print(f"purged shells: {purged_decks:,} decks, {purged_rows:,} field-name rows")
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
        "rejected_decks": rejected,
        "rejected_field_names": n_field,
        "rejected_too_few_resolvable": n_few,
        "purged_shell_decks": purged_decks,
        "purged_field_name_rows": purged_rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Load JSONL corpus into decks.sqlite + edhrec.sqlite")
    ap.add_argument("--corpus", default=str(ROOT / "data" / "decklists"))
    ap.add_argument("--out", default=str(ROOT / "data"))
    ap.add_argument("--scores", default=str(ROOT / "data" / "scores.sqlite"),
                    help="scores sqlite whose cards.name column resolves card names")
    args = ap.parse_args()
    stats = load(Path(args.corpus), Path(args.out), scores_db=Path(args.scores))
    print(f"decks.sqlite:  {stats['unique_decks']:,} unique decks "
          f"({stats['deck_records_read']:,} records read)")
    print(f"edhrec.sqlite: {stats['unique_commanders']:,} commanders, "
          f"{stats['edhrec_metric_rows']:,} metric rows")
    print(f"files: {stats['files']}  |  skipped lines: {stats['skipped']:,}  |  "
          f"rejected decks: {stats['rejected_decks']:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
