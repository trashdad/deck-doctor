"""Shared plumbing for the ranking backtests (tools/eval/backtest_*.py).

Read-only. Loads the LIVE backend Store (Postgres named by DATABASE_URL — use the
deckdoctor_test copy, never prod) and the scraped corpus in data/decks.sqlite.

Design + results: docs/plans/2026-11-24-ranking-eval.md.

LEAKAGE CAVEAT: co-occurrence and EDHREC tables were built FROM (or alongside) these
same corpus decks, so absolute numbers are optimistic. They are valid for RELATIVE
comparison of weight settings on the same decks only.
"""

from __future__ import annotations

import json
import os
import random
import sqlite3
import sys
import zlib
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

RESULTS_DIR = Path(__file__).resolve().parent / "results"
DECKS_DB = ROOT / "data" / "decks.sqlite"
DECK_SIDE = 99            # non-commander cards in a legal Commander deck
MIN_DISTINCT = 60         # basics are collapsed in the corpus; below this a list is partial
MIN_RESOLVED = 0.95       # share of a deck's names that must resolve to a card id
PER_COMMANDER_CAP = 5     # stop a few popular commanders dominating the sample
TRAIN_SHARE = 7           # out of 10: commander-disjoint 70 / 30 train / held-out split
_FINGERPRINT: dict | None = None
BASIC_NAMES = {"W": "plains", "U": "island", "B": "swamp", "R": "mountain", "G": "forest"}


def db_name() -> str:
    """Database NAME only (never the DSN: it may carry credentials)."""
    from app import config
    return (urlparse(config.DATABASE_URL).path or "").lstrip("/").split("?")[0]


def load_store():
    """Build the live Store and refuse to run on a half-loaded DB (another agent's tests
    may rename the combo tables aside for a moment; the Store reads them once)."""
    global _FINGERPRINT
    _FINGERPRINT = code_fingerprint()   # taken when the modules are imported, not at exit
    from app.store import get_store
    if os.environ.get("DATABASE_URL") is None:
        raise SystemExit("set DATABASE_URL (e.g. postgresql://deckdoctor@localhost/deckdoctor_test)")
    store = get_store()
    sizes = {"cards": len(store._cards), "edhrec_pages": len(store._edhrec),
             "spellbook": len(store._spellbook), "engines": len(store._engines),
             "staples": len(store._staples)}
    if not all(sizes.values()):
        raise SystemExit(f"Store looks partially loaded, refusing to evaluate: {sizes}")
    return store, sizes


class CachedStore:
    """Memoises the per-card neighbour reads (pure DB lookups) so re-running the same
    deck under many weight settings costs no extra queries. Everything else passes
    through to the real Store unchanged."""

    def __init__(self, store):
        self._s = store
        self._cooc: dict = {}
        self._syn: dict = {}
        self._cmds = None

    def __getattr__(self, name):
        return getattr(self._s, name)

    def cooccurrence_neighbors(self, cid, limit=30):
        key = (cid, limit)
        if key not in self._cooc:
            self._cooc[key] = self._s.cooccurrence_neighbors(cid, limit)
        return self._cooc[key]

    def synergy_neighbors(self, cid, limit=30):
        key = (cid, limit)
        if key not in self._syn:
            self._syn[key] = self._s.synergy_neighbors(cid, limit)
        return self._syn[key]

    def commanders(self, q="", colors="", sort="popularity", limit=0):
        if (q, colors, sort, limit) != ("", "", "popularity", 0):
            return self._s.commanders(q=q, colors=colors, sort=sort, limit=limit)
        if self._cmds is None:
            self._cmds = self._s.commanders(limit=0)
        return self._cmds


def split_of(commander: str) -> str:
    """Stable commander-disjoint split (crc32, not the salted hash())."""
    return "train" if zlib.crc32(commander.encode("utf-8")) % 10 < TRAIN_SHARE else "test"


def basic_ids(store, ci: set[str]) -> list[str]:
    names = [BASIC_NAMES[c] for c in "WUBRG" if c in ci] or ["wastes"]
    return [store._name_to_id[n] for n in names if n in store._name_to_id]


def load_corpus(store, need_page: bool = True) -> list[dict]:
    """Eligible, de-duplicated corpus decks.

    Each: {deck_id, source, commander, cmd_id, ids (distinct resolved non-commander
    card ids, sorted), split}. Eligible = commander resolves to a legal commander
    (with an EDHREC page when need_page), >= MIN_RESOLVED of names resolve, and
    MIN_DISTINCT <= distinct cards <= DECK_SIDE. Identical lists are kept once.
    """
    from app.suggest import is_commander
    con = sqlite3.connect(f"file:{DECKS_DB}?mode=ro", uri=True)
    meta = {d: (s, c) for d, s, c in con.execute("SELECT deck_id, source, commander FROM decks")}
    names: dict[str, list[str]] = {}
    for deck_id, name in con.execute("SELECT deck_id, card_name FROM deck_cards ORDER BY deck_id, card_name"):
        names.setdefault(deck_id, []).append(name)
    con.close()

    out, seen = [], set()
    for deck_id in sorted(meta):
        source, commander = meta[deck_id]
        if not commander:
            continue
        cmd_id = store._name_to_id.get(commander.lower())
        cmd = store.get(cmd_id) if cmd_id else None
        if cmd is None or not is_commander(cmd):
            continue
        if need_page and not store.edhrec_for(cmd_id):
            continue
        rows = [n for n in names.get(deck_id, []) if (n or "").lower() != commander.lower()]
        ids = {store._name_to_id.get((n or "").lower()) for n in rows}
        resolved = {i for i in ids if i and i != cmd_id}
        if not rows or len(resolved) / len(set(rows)) < MIN_RESOLVED:
            continue
        if not (MIN_DISTINCT <= len(resolved) <= DECK_SIDE):
            continue
        key = (cmd_id, frozenset(resolved))
        if key in seen:
            continue
        seen.add(key)
        out.append({"deck_id": deck_id, "source": source, "commander": cmd["name"],
                    "cmd_id": cmd_id, "ids": sorted(resolved), "split": split_of(cmd["name"])})
    return out


def sample(decks: list[dict], n: int, seed: int) -> list[dict]:
    """Deterministic sample: seeded order, at most PER_COMMANDER_CAP per commander."""
    order = sorted(decks, key=lambda d: zlib.crc32(f"{seed}:{d['deck_id']}".encode()))
    per: dict[str, int] = {}
    out = []
    for d in order:
        if per.get(d["cmd_id"], 0) >= PER_COMMANDER_CAP:
            continue
        per[d["cmd_id"]] = per.get(d["cmd_id"], 0) + 1
        out.append(d)
        if len(out) >= n:
            break
    return out


def rng_for(seed: int, deck_id: str) -> random.Random:
    return random.Random(zlib.crc32(f"{seed}:{deck_id}".encode()))


def mean(xs) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else float("nan")


def paired_bootstrap(a: list[float], b: list[float], seed: int, n: int = 2000) -> dict:
    """Mean of (b - a) per deck with a 95 % percentile bootstrap CI (decks resampled)."""
    diffs = [y - x for x, y in zip(a, b)]
    if not diffs:
        return {"mean_diff": None, "ci95": [None, None], "n": 0}
    rng = random.Random(seed)
    k = len(diffs)
    boots = sorted(sum(diffs[rng.randrange(k)] for _ in range(k)) / k for _ in range(n))
    return {"mean_diff": round(mean(diffs), 4),
            "ci95": [round(boots[int(0.025 * n)], 4), round(boots[int(0.975 * n) - 1], 4)],
            "n": k}


def code_fingerprint() -> dict:
    """sha256[:12] of the ranking code a result depends on (the working tree may hold
    uncommitted edits, so a git hash alone would not identify what was measured)."""
    import hashlib
    files = ("cut_to_100.py", "doctor.py", "pivot.py", "suggest.py", "store.py")
    return {f: hashlib.sha256((ROOT / "backend" / "app" / f).read_bytes()).hexdigest()[:12]
            for f in files}


def write_json(name: str, payload: dict) -> Path:
    payload = {**payload, "code_sha256_12": _FINGERPRINT or code_fingerprint()}
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def table(rows: list[list], header: list[str]) -> str:
    cells = [header] + [[f"{c:.4f}" if isinstance(c, float) else str(c) for c in r] for r in rows]
    w = [max(len(r[i]) for r in cells) for i in range(len(header))]
    lines = ["  ".join(c.ljust(w[i]) for i, c in enumerate(r)) for r in cells]
    lines.insert(1, "  ".join("-" * x for x in w))
    return "\n".join(lines)
