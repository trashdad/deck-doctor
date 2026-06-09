#!/usr/bin/env python3
"""Offline pipeline: Scryfall-format card JSON -> query-ready SQLite store.

This is the "translation algorithm" from Doc A. It runs on home hardware, fully
offline, so the live web app never thinks — it does O(1) lookups against the
artifact this script emits.

What it produces (SQLite at --out):
  * cards      : id, name, ier, mechanic_tags (json), parasitic (json), + raw fields
  * synergies  : (card_a, card_b) -> css, der, lift   [top-K neighbours per card]

Scale note: a full 32k x 32k DER matrix is ~5e8 pairs and impractical to store.
We instead persist per-card IER + tags for every card, and materialize only the
top-K highest-CSS neighbours per card (plus all same-parasitic-cluster pairs).
DER for any arbitrary pair is still O(1) at query time: look up both IERs + tags
and apply the formula. The FAISS/embedding ANN path (for semantic neighbours at
full scale) plugs in at `_candidate_neighbours` — see docs/architecture.md.

Usage:
  python build_store.py --cards ../data/sample_cards.json --out ../data/scores.sqlite --top-k 16
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
import time
from pathlib import Path

# Make the package importable when run as a script from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from simmander_scoring.evaluate import (  # noqa: E402
    combinatorial_synergy_score,
    dynamic_efficiency_ratio,
    has_lift,
    isolated_efficiency_rating,
)
from simmander_scoring.mechanics import tag_card  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("build_store")


def _progress(iterable, total: int, desc: str):
    """tqdm if available, else a dependency-free fallback bar."""
    try:
        from tqdm import tqdm  # type: ignore

        return tqdm(iterable, total=total, desc=desc, unit="card")
    except ImportError:
        def gen():
            start = time.time()
            for i, item in enumerate(iterable, 1):
                if i % max(1, total // 20) == 0 or i == total:
                    pct = 100 * i / total
                    log.info("%s: %d/%d (%.0f%%) %.1fs", desc, i, total, pct, time.time() - start)
                yield item

        return gen()


def load_cards(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    # Accept either a bare list or a Scryfall {"data": [...]} envelope.
    cards = data["data"] if isinstance(data, dict) and "data" in data else data
    log.info("Loaded %d cards from %s", len(cards), path)
    return cards


def _candidate_neighbours(
    cards: list[dict],
    tags: list,
    max_per_card: int = 300,
) -> list[tuple[int, int]]:
    """Return index pairs to score via tag-bucketed inverted index.

    Only returns pairs that share at least one mechanic tag (or are in a
    complementary producer/payoff relationship), keeping pairs per card capped
    at max_per_card to bound runtime on large corpora.
    """
    from collections import defaultdict
    from simmander_scoring.mechanics import COMPLEMENTARY_PAIRS

    # inverted index: tag -> sorted list of card indices
    by_tag: dict[str, list[int]] = defaultdict(list)
    for i, t in enumerate(tags):
        for tag in t.mechanic_tags | {f"parasitic:{p}" for p in t.parasitic}:
            by_tag[tag].append(i)

    # also add complementary cross-pairs (producer -> payoff)
    comp_index: dict[str, list[int]] = defaultdict(list)
    for producer, payoff in COMPLEMENTARY_PAIRS:
        comp_index[producer].extend(by_tag.get(payoff, []))
        comp_index[payoff].extend(by_tag.get(producer, []))

    seen: set[tuple[int, int]] = set()
    pairs: list[tuple[int, int]] = []

    for i, t in enumerate(tags):
        candidates: set[int] = set()
        for tag in t.mechanic_tags | {f"parasitic:{p}" for p in t.parasitic}:
            candidates.update(by_tag.get(tag, []))
            candidates.update(comp_index.get(tag, []))
        candidates.discard(i)

        # cap so common tags (removal, ramp) don't explode
        capped = sorted(candidates)[:max_per_card]
        for j in capped:
            key = (min(i, j), max(i, j))
            if key not in seen:
                seen.add(key)
                pairs.append(key)

    return pairs


def build(cards: list[dict], out: Path, top_k: int) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    conn = sqlite3.connect(out)
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE cards (
            id TEXT PRIMARY KEY,
            name TEXT,
            cmc REAL,
            type_line TEXT,
            colors TEXT,
            color_identity TEXT,
            image_normal TEXT,
            ier REAL,
            mechanic_tags TEXT,
            parasitic TEXT
        );
        CREATE TABLE synergies (
            card_a TEXT,
            card_b TEXT,
            css REAL,
            der REAL,
            lift INTEGER,
            PRIMARY KEY (card_a, card_b)
        );
        CREATE INDEX idx_syn_a ON synergies(card_a, der DESC);
        CREATE INDEX idx_syn_b ON synergies(card_b, der DESC);
        """
    )

    # Pass 1: per-card IER + tags.
    tags = []
    iers = []
    for card in _progress(cards, len(cards), "IER + tags"):
        t = tag_card(card)
        tags.append(t)
        ier = isolated_efficiency_rating(card)
        iers.append(ier)
        img = (card.get("image_uris") or {}).get("normal", "")
        cur.execute(
            "INSERT INTO cards VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                card.get("id"),
                card.get("name"),
                card.get("cmc"),
                card.get("type_line"),
                json.dumps(card.get("colors") or []),
                json.dumps(card.get("color_identity") or []),
                img,
                ier,
                json.dumps(sorted(t.mechanic_tags)),
                json.dumps(sorted(t.parasitic)),
            ),
        )
    conn.commit()

    # Pass 2: pairwise CSS/DER, keep top-K per card + all Lift pairs.
    pairs = _candidate_neighbours(cards, tags)
    log.info("Scoring %d candidate pairs", len(pairs))
    # bucket[card_index] = list of (der, other_index, css, lift)
    buckets: dict[int, list[tuple[float, int, float, bool]]] = {i: [] for i in range(len(cards))}
    lift_pairs: list[tuple[int, int, float, float, bool]] = []

    for i, j in _progress(pairs, len(pairs), "CSS/DER"):
        css = combinatorial_synergy_score(tags[i], tags[j])
        lift = has_lift(tags[i], tags[j])
        if css <= 0.0 and not lift:
            continue
        der = dynamic_efficiency_ratio(iers[i], iers[j], css)
        buckets[i].append((der, j, css, lift))
        buckets[j].append((der, i, css, lift))
        if lift:
            lift_pairs.append((i, j, css, der, lift))

    # Materialize: top-K neighbours per card (deduped) + every Lift pair.
    seen: set[tuple[str, str]] = set()
    rows: list[tuple[str, str, float, float, int]] = []

    def add(ai: int, bi: int, css: float, der: float, lift: bool) -> None:
        a, b = cards[ai].get("id"), cards[bi].get("id")
        key = tuple(sorted((a, b)))  # type: ignore[arg-type]
        if key in seen:
            return
        seen.add(key)
        rows.append((key[0], key[1], css, der, int(lift)))

    for i, entries in buckets.items():
        entries.sort(reverse=True)  # by DER desc
        for der, j, css, lift in entries[:top_k]:
            add(i, j, css, der, lift)
    for i, j, css, der, lift in lift_pairs:
        add(i, j, css, der, lift)

    cur.executemany(
        "INSERT OR IGNORE INTO synergies VALUES (?,?,?,?,?)", rows
    )
    conn.commit()
    log.info("Wrote %d cards, %d synergy rows -> %s", len(cards), len(rows), out)
    conn.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the query-ready synergy store.")
    ap.add_argument("--cards", type=Path, required=True, help="Scryfall-format JSON")
    ap.add_argument("--out", type=Path, required=True, help="Output SQLite path")
    ap.add_argument("--top-k", type=int, default=16, help="Neighbours kept per card")
    args = ap.parse_args(argv)

    start = time.time()
    cards = load_cards(args.cards)
    build(cards, args.out, args.top_k)
    log.info("Done in %.2fs", time.time() - start)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
