"""SP10 — evaluation harness: reconstruct real decks to score the suggestion engine.

Reuses the LIVE backend engine (no reimplementation): hide N cards from a real deck,
ask app.suggest.recommend to rebuild it, measure recall@k and MRR. Supports a weight
grid search on the train split. stdlib + the backend app (already installed).

LEAKAGE CAVEAT: the co-occurrence and EDHREC tables were built FROM these same decks,
so absolute numbers are optimistic. Valid for RELATIVE comparison only (weights A vs B,
engine vs baseline).

CLI: python scoring/eval_suggest.py --decks data/decks.sqlite --holdout 10 --limit 50
       [--weights 0.45,0.30,0.15,0.10] [--grid] [--split test|train|all] [--max-decks N]
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import suggest                       # noqa: E402
from app.doctor import category_of            # noqa: E402
from app.store import get_store               # noqa: E402

CAVEAT = ("LEAKAGE CAVEAT: co-occurrence and EDHREC tables were built FROM these same "
          "decks; absolute numbers are optimistic. Valid for RELATIVE comparison "
          "(weights A vs B, engine vs baseline) only.")


# ---- pure metrics (unit-tested) ------------------------------------------
def split_of(deck_id: str) -> str:
    """Stable train/test split via crc32 (NOT salted hash())."""
    return "train" if zlib.crc32(deck_id.encode("utf-8")) % 2 == 0 else "test"


def recall_at_k(ranked: list[str], hidden: set[str], k: int) -> float:
    if not hidden:
        return 0.0
    return len(set(ranked[:k]) & hidden) / len(hidden)


def mrr(ranked: list[str], hidden: set[str]) -> float:
    if not hidden:
        return 0.0
    total = 0.0
    rank_of = {cid: i + 1 for i, cid in enumerate(ranked)}
    for h in hidden:
        if h in rank_of:
            total += 1.0 / rank_of[h]
    return total / len(hidden)


def pick_holdout(deck_id: str, candidates: list[str], k: int) -> set[str]:
    """Deterministic hidden set seeded by deck_id."""
    rng = random.Random(deck_id)
    pool = list(candidates)
    rng.shuffle(pool)
    return set(pool[:k])


# ---- deck loading --------------------------------------------------------
def load_decks(db_path: Path) -> list[tuple[str, str, list[str]]]:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    decks = con.execute("SELECT deck_id, commander FROM decks").fetchall()
    cards_by_deck: dict[str, list[str]] = {}
    for deck_id, name in con.execute("SELECT deck_id, card_name FROM deck_cards"):
        cards_by_deck.setdefault(deck_id, []).append(name)
    con.close()
    return [(d, c, cards_by_deck.get(d, [])) for d, c in decks]


def eligible(store, commander: str | None, names: list[str]):
    """-> (cmd_id, resolved_nonland_ids) if eligible (cmd resolves, >=30 cards), else None."""
    if not commander:
        return None
    cmd_id = store._name_to_id.get(commander.lower())
    if cmd_id is None:
        return None
    resolved = []
    for n in names:
        cid = store._name_to_id.get((n or "").lower())
        if cid and cid != cmd_id:
            resolved.append(cid)
    if len(resolved) < 30:
        return None
    nonland = [c for c in resolved
               if category_of(store.get(c)) != "land"]
    return cmd_id, resolved, nonland


# ---- evaluation ----------------------------------------------------------
def eval_deck(store, cmd_id, resolved, nonland, deck_id, holdout, limit) -> dict | None:
    hidden = pick_holdout(deck_id, nonland, holdout)
    if not hidden:
        return None
    input_ids = [c for c in resolved if c not in hidden]
    res = suggest.recommend(store, cmd_id, input_ids, limit=limit)
    ranked = [s["card"]["id"] for s in res["suggestions"]]
    # popularity baseline: in-CI staples by deck frequency
    ci = set(store.get(cmd_id)["color_identity"])
    base = [c for c, _f in store.staples_for_colors(ci, limit=limit * 2,
            exclude=set(input_ids) | {cmd_id})][:limit]
    return {
        "tier": res["tier"],
        "r10": recall_at_k(ranked, hidden, 10),
        "r25": recall_at_k(ranked, hidden, 25),
        "r50": recall_at_k(ranked, hidden, 50),
        "mrr": mrr(ranked, hidden),
        "base_r25": recall_at_k(base, hidden, 25),
        "base_mrr": mrr(base, hidden),
    }


def aggregate(rows: list[dict]) -> dict:
    n = len(rows)
    if n == 0:
        return {"n_decks": 0}
    keys = ["r10", "r25", "r50", "mrr", "base_r25", "base_mrr"]
    out = {"n_decks": n}
    for k in keys:
        out[k] = round(sum(r[k] for r in rows) / n, 4)
    tiers: dict[str, int] = {}
    for r in rows:
        tiers[r["tier"]] = tiers.get(r["tier"], 0) + 1
    out["tiers"] = tiers
    return out


def run_eval(store, decks, split, holdout, limit, max_decks) -> dict:
    rows = []
    for deck_id, commander, names in decks:
        if split != "all" and split_of(deck_id) != split:
            continue
        elig = eligible(store, commander, names)
        if elig is None:
            continue
        cmd_id, resolved, nonland = elig
        if len(nonland) <= holdout:
            continue
        r = eval_deck(store, cmd_id, resolved, nonland, deck_id, holdout, limit)
        if r:
            rows.append(r)
        if max_decks and len(rows) >= max_decks:
            break
    return aggregate(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate the SP5 suggestion engine.")
    ap.add_argument("--decks", default=str(ROOT / "data" / "decks.sqlite"))
    ap.add_argument("--holdout", type=int, default=10)
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--weights", default=None, help="w_edh,w_cooc,w_struct,w_engine")
    ap.add_argument("--grid", action="store_true")
    ap.add_argument("--split", choices=["train", "test", "all"], default="all")
    ap.add_argument("--max-decks", type=int, default=0)
    args = ap.parse_args()

    print(CAVEAT)
    print()
    store = get_store()
    decks = load_decks(Path(args.decks))
    print(f"loaded {len(decks)} decks from {args.decks}")

    if args.weights:
        w = [float(x) for x in args.weights.split(",")]
        suggest.WEIGHTS.update({"edh": w[0], "cooc": w[1], "struct": w[2], "engine": w[3]})

    result: dict = {"caveat": CAVEAT, "config": vars(args)}

    if args.grid:
        grid = []
        for w_edh in (0.3, 0.4, 0.5, 0.6):
            for w_cooc in (0.1, 0.2, 0.3, 0.4):
                for w_struct in (0.05, 0.15, 0.25):
                    s = w_edh + w_cooc + w_struct + 0.10
                    if not (0.9 <= s <= 1.1):
                        continue
                    grid.append((w_edh / s, w_cooc / s, w_struct / s, 0.10 / s))
        print(f"grid: {len(grid)} weight combos on the TRAIN split\n")
        best = None
        rows = []
        for combo in grid:
            suggest.WEIGHTS.update({"edh": combo[0], "cooc": combo[1],
                                    "struct": combo[2], "engine": combo[3]})
            agg = run_eval(store, decks, "train", args.holdout, args.limit, args.max_decks)
            rows.append((combo, agg))
            tag = "/".join(f"{c:.2f}" for c in combo)
            print(f"  {tag}  r25={agg.get('r25')}  mrr={agg.get('mrr')}  (n={agg.get('n_decks')})")
            if best is None or agg.get("r25", 0) > best[1].get("r25", 0):
                best = (combo, agg)
        suggest.WEIGHTS.update({"edh": best[0][0], "cooc": best[0][1],
                                "struct": best[0][2], "engine": best[0][3]})
        test_agg = run_eval(store, decks, "test", args.holdout, args.limit, args.max_decks)
        print(f"\nWINNER weights={[round(c,3) for c in best[0]]}")
        print(f"  TRAIN r25={best[1].get('r25')}  TEST r25={test_agg.get('r25')} "
              f"mrr={test_agg.get('mrr')}")
        result["grid_winner"] = {"weights": list(best[0]), "train": best[1], "test": test_agg}
    else:
        agg = run_eval(store, decks, args.split, args.holdout, args.limit, args.max_decks)
        print(f"\nsplit={args.split}  n_decks={agg.get('n_decks')}")
        print(f"  recall@10 = {agg.get('r10')}")
        print(f"  recall@25 = {agg.get('r25')}   (popularity baseline = {agg.get('base_r25')})")
        print(f"  recall@50 = {agg.get('r50')}")
        print(f"  MRR       = {agg.get('mrr')}   (popularity baseline = {agg.get('base_mrr')})")
        print(f"  tiers     = {agg.get('tiers')}")
        result["aggregate"] = agg

    out_path = ROOT / "data" / "eval_results.json"
    out_path.write_text(json.dumps(result, indent=2))
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
