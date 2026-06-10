"""SP10 — evaluation harness: reconstruct real decks to score the suggestion engine.

SCAFFOLD — implement per docs/superpowers/plans/2026-06-10-sp6-sp11-roadmap.md §10.1.
stdlib-only. Reuses the LIVE backend engine (no reimplementation):

    sys.path.insert(0, str(REPO_ROOT / "backend"))
    from app.store import get_store
    from app import suggest

Protocol (binding — the roadmap §10.1 numbers every step):
1. Eligible deck: commander resolves via store._name_to_id AND >= 30 mainboard cards resolve.
2. Split: hash(deck_id) % 2 → 0 train / 1 test (stable; use zlib.crc32 of the utf-8 deck_id,
   NOT Python's salted hash()).
3. Holdout: rng = random.Random(deck_id); hide `--holdout` (default 10) resolvable nonland,
   non-commander cards.
4. suggest.recommend(store, cmd_id, remaining_ids, limit=--limit (default 50)).
5. Metrics per deck: recall@{10,25,50}, MRR over the hidden set (1/rank, 0 if absent).
6. Aggregate means; per-tier breakdown; ALWAYS also report the popularity baseline
   (store.staples_for_colors(commander CI) ranking scored with the same metrics).
7. --grid: weight search on TRAIN ONLY over
   w_edh in {0.3,0.4,0.5,0.6} x w_cooc in {0.1,0.2,0.3,0.4} x w_struct in {0.05,0.15,0.25},
   w_engine fixed at 0.10; renormalize each combo; patch suggest.WEIGHTS (restore after);
   rank by recall@25; print the winner's TEST metrics last.
8. Output: aligned text table to stdout + JSON to data/eval_results.json (gitignored).

REQUIRED report header (print verbatim):
  "LEAKAGE CAVEAT: co-occurrence and EDHREC tables were built FROM these same decks;
   absolute numbers are optimistic. Valid for RELATIVE comparison (weights A vs B,
   engine vs baseline) only."

CLI: python scoring/eval_suggest.py --decks data/decks.sqlite --holdout 10 --limit 50
       [--weights 0.45,0.30,0.15,0.10] [--grid] [--split test|train|all] [--max-decks N]
"""

from __future__ import annotations


def main() -> None:
    raise NotImplementedError("SP10 pending — roadmap §10.1")


if __name__ == "__main__":
    main()
