"""Precon-noise audit (read-only).

Measures, per commander, how many decks in data/decks.sqlite look like stock
preconstructed decks.

Two detectors:
  1. Known-precon match: a deck is "precon-like" if >= N of its cards (default 85)
     match a known precon list. Precon lists are loaded from a JSON file
     ({"Precon Name": {"commander": "...", "cards": [...]}, ...}) passed with
     --precons. No precon list ships with the repo: if the file is missing the
     detector reports UNKNOWN.
  2. Exact-duplicate proxy (always runs): decks whose full card set is identical
     to another deck of the same commander. Unmodified precons (and copy-pasted
     netdecks) show up as identical lists; this gives a lower bound on noise
     without any external data.

Usage: python -I tools/audit/precon_noise_audit.py [--db data/decks.sqlite]
       [--precons precons.json] [--min-match 85] [--top 20]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import time
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def load_precons(path: Path | None) -> dict[str, set[str]]:
    if not path or not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {name: set(v["cards"]) for name, v in data.items() if not name.startswith("_")}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(REPO / "data" / "decks.sqlite"))
    ap.add_argument("--precons", default=None)
    ap.add_argument("--min-match", type=int, default=85)
    ap.add_argument("--min-frac", type=float, default=0.85,
                    help="also count a deck as precon-like if its overlap covers >= this fraction "
                         "of a precon's distinct card names (basic lands collapse to one name, "
                         "so most precon lists have < 85 distinct names)")
    ap.add_argument("--top", type=int, default=20)
    a = ap.parse_args()

    t0 = time.time()
    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    precons = load_precons(Path(a.precons) if a.precons else None)

    decks: dict[str, tuple[str, str]] = {}  # deck_id -> (commander, source)
    for deck_id, source, commander in con.execute("SELECT deck_id, source, commander FROM decks"):
        decks[deck_id] = (commander or "?", source)

    cards: dict[str, list[str]] = defaultdict(list)
    for deck_id, name in con.execute("SELECT deck_id, card_name FROM deck_cards ORDER BY deck_id, card_name"):
        cards[deck_id].append(name)

    per_cmd_total: dict[str, int] = defaultdict(int)
    per_cmd_dupe: dict[str, int] = defaultdict(int)
    per_cmd_precon: dict[str, int] = defaultdict(int)
    hash_groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    best_frac: dict[str, float] = {}

    for deck_id, (cmd, _src) in decks.items():
        per_cmd_total[cmd] += 1
        cl = cards.get(deck_id, [])
        h = hashlib.sha1("\n".join(cl).encode()).hexdigest()
        hash_groups[(cmd, h)].append(deck_id)
        if precons:
            cs = set(cl)
            best = max((len(cs & pc) / max(len(pc), 1) for pc in precons.values()), default=0.0)
            best_frac[deck_id] = best
            if best >= a.min_frac or any(len(cs & pc) >= a.min_match for pc in precons.values()):
                per_cmd_precon[cmd] += 1

    dupe_decks = 0
    for (cmd, _h), ids in hash_groups.items():
        if len(ids) > 1:
            per_cmd_dupe[cmd] += len(ids)
            dupe_decks += len(ids)

    n_decks = len(decks)
    n_cmd = len(per_cmd_total)
    print(f"decks={n_decks} commanders={n_cmd} decks_with_cards={len(cards)}")
    print(f"exact-duplicate decks (same commander, identical list): {dupe_decks} "
          f"({100.0 * dupe_decks / max(n_decks, 1):.2f}%)")
    if precons:
        tot = sum(per_cmd_precon.values())
        print(f"precon-like decks (>= {a.min_match} cards or >= {a.min_frac:.0%} of a known precon's "
              f"distinct names, {len(precons)} lists): {tot} ({100.0 * tot / max(n_decks, 1):.2f}%)")
        for lo in (0.95, 0.85, 0.70, 0.50):
            k = sum(1 for v in best_frac.values() if v >= lo)
            print(f"  best-overlap >= {lo:.0%} of a precon: {k:5d} ({100.0 * k / max(n_decks, 1):.2f}%)")
    else:
        print("precon-like decks (known-list detector): UNKNOWN - no precon list JSON supplied (--precons)")

    print(f"\nTop {a.top} commanders by exact-duplicate share (min 20 decks):")
    rows = [(c, per_cmd_dupe[c], per_cmd_total[c]) for c in per_cmd_total if per_cmd_total[c] >= 20]
    rows.sort(key=lambda r: (-r[1] / r[2], -r[2]))
    for c, d, t in rows[: a.top]:
        print(f"  {c:40s} dupes={d:5d} / {t:5d} ({100.0 * d / t:5.1f}%)  precon_like={per_cmd_precon.get(c, 0) if precons else 'UNKNOWN'}")
    print(f"\nelapsed {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
