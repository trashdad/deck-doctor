"""Continuous corpus-refresh daemon — keeps recommendations current as new decks arrive.

This is the always-on counterpart to the one-shot pipeline. Each cycle it:

  1. SCRAPE  — pull more real decklists from EDHREC/Archidekt/Moxfield
               (tools/scrape_decklists/runner.py seeds; resumable, dedup-by-deck_id).
  2. LOAD    — fold the grown JSONL into decks.sqlite + edhrec.sqlite
               (tools/scrape_decklists/load_corpus.py; idempotent).
  3. REBUILD — recompute the synergy tables the engine reads:
               scoring/build_relationships.py  → card_relationships, engines
               scoring/build_cooccurrence.py   → card_cooccurrence, re-fused synergy
  4. RELOAD  — POST /admin/reload so the running backend swaps in the new tables
               WITHOUT a restart. New decks now change live recommendations.

The user-facing effect: a player adding cards already gets instant per-request
re-ranking (the engine recomputes every call); this loop additionally widens the
*evidence base* over time, so the same deck earns better suggestions as the corpus grows.

stdlib-only. Run alongside the backend:
    python tools/refresh_loop.py --interval 1800 --top 60 --decks-per 20
    python tools/refresh_loop.py --once          # a single cycle, then exit
    python tools/refresh_loop.py --no-rebuild     # scrape+load only (cheap), reload skipped
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
COMBO_CATALOG = Path("C:/simmander/simmander/data/combo_catalog.json")
KNOWN_COMBOS = Path("C:/simmander/simmander/data/known_combos.json")


def _run(cmd: list[str], label: str) -> bool:
    print(f"[refresh] {label}: {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd, cwd=str(ROOT))
    if proc.returncode != 0:
        print(f"[refresh] {label} FAILED (exit {proc.returncode}) — skipping rest of cycle",
              flush=True)
        return False
    return True


def _reload(api: str) -> None:
    try:
        req = urllib.request.Request(f"{api}/admin/reload", method="POST")
        with urllib.request.urlopen(req, timeout=120) as r:
            print(f"[refresh] reloaded: {r.read().decode()}", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"[refresh] reload skipped ({e}) — is the backend running on {api}?", flush=True)


def cycle(args) -> None:
    scrape = [PY, "tools/scrape_decklists/runner.py", "seeds",
              "--top", str(args.top), "--decks-per", str(args.decks_per),
              "--max-commanders", str(args.max_commanders), "--batch", "loop"]
    if not _run(scrape, "scrape"):
        return
    if not _run([PY, "tools/scrape_decklists/load_corpus.py"], "load_corpus"):
        return
    if args.no_rebuild:
        print("[refresh] --no-rebuild: skipping rebuild + reload", flush=True)
        return

    rel = [PY, "scoring/build_relationships.py", "--db", "data/scores.sqlite"]
    if COMBO_CATALOG.exists():
        rel += ["--catalog", str(COMBO_CATALOG)]
    if KNOWN_COMBOS.exists():
        rel += ["--catalog", str(KNOWN_COMBOS)]
    if not _run(rel, "build_relationships"):
        return
    cooc = [PY, "scoring/build_cooccurrence.py", "--scores", "data/scores.sqlite",
            "--decks", "data/decks.sqlite", "--edhrec", "data/edhrec.sqlite",
            "--min-support", "20"]
    if not _run(cooc, "build_cooccurrence"):
        return
    _reload(args.api)


def main() -> int:
    ap = argparse.ArgumentParser(description="Continuous corpus refresh daemon.")
    ap.add_argument("--interval", type=int, default=1800, help="seconds between cycles")
    ap.add_argument("--top", type=int, default=60, help="EDHREC top-N commanders to seed")
    ap.add_argument("--decks-per", type=int, default=20)
    ap.add_argument("--max-commanders", type=int, default=60)
    ap.add_argument("--api", default="http://localhost:8001")
    ap.add_argument("--no-rebuild", action="store_true",
                    help="scrape + load only (skip the heavy rebuild + reload)")
    ap.add_argument("--once", action="store_true", help="run one cycle, then exit")
    args = ap.parse_args()

    while True:
        start = time.monotonic()
        print(f"[refresh] cycle start", flush=True)
        try:
            cycle(args)
        except KeyboardInterrupt:
            print("[refresh] interrupted", flush=True)
            return 0
        except Exception as e:  # noqa: BLE001
            print(f"[refresh] cycle error: {e}", flush=True)
        if args.once:
            return 0
        elapsed = time.monotonic() - start
        sleep_for = max(args.interval - elapsed, 30)
        print(f"[refresh] cycle done in {elapsed:.0f}s; sleeping {sleep_for:.0f}s", flush=True)
        time.sleep(sleep_for)


if __name__ == "__main__":
    raise SystemExit(main())
