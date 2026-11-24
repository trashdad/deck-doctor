"""Backtest: does find_pivots rank the commanders a 99 was really built for?

Method (full write-up: docs/plans/2026-11-24-ranking-eval.md):
  * Own-commander recovery. Take a real corpus deck of commander A, drop A, and ask
    find_pivots (no current commander) to rank every candidate. A good "which
    commander fits this 99" scorer must put A at or near the top. Two variants:
      full    — the whole list (near-saturated: MRR ~0.9, so a weak discriminator);
      partial — PARTIAL_N random non-basic cards of it (a deck in progress; harder,
                and the variant the weights are tuned on).
    Metrics: MRR, hit@1, hit@5, hit@10 of A.
  * Neighbour surfacing (secondary). For each eval deck of A, find the most similar
    corpus deck (Jaccard over distinct non-basic cards) built on a DIFFERENT
    commander B that has an EDHREC page. When Jaccard >= NEIGHBOUR_J, B is a real
    alternative somebody built nearly this list on; measure hit@10 / MRR of B among
    candidates with A removed (i.e. what the UI shows with A as the current commander).
  * Grid-search the four weights on the TRAIN commanders (70 %); choose with a
    pre-registered rule; compare chosen vs invented on the HELD-OUT commanders (30 %).

Rescoring uses app.pivot.pivot_score (the production formula) on components computed
exactly as score_commander does; the script asserts that, at the production weights,
its ranking reproduces find_pivots' order for every deck.

Usage (read-only; never point it at prod):
  DATABASE_URL=postgresql://deckdoctor@localhost/deckdoctor_test \
      python -I tools/eval/backtest_pivot.py [--decks 600] [--seed 20261124]
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

from app import pivot  # noqa: E402

NEIGHBOUR_J = 0.4     # top ~8 % of nearest-neighbour overlaps in this corpus (median ~0.21)
PARTIAL_N = 30        # deck-in-progress variant: 30 random non-basic cards of the 99
INVENTED = (0.5, 0.3, 0.2, 1.0)
GRID_COV = (0.0, 0.25, 0.5, 1.0)
GRID_INC = (0.0, 0.15, 0.3, 0.6, 1.0)
GRID_SYN = (0.0, 0.1, 0.2, 0.4, 0.8)
GRID_OFF = (0.0, 0.25, 0.5, 1.0, 2.0, 4.0)


def components(store, deck_cards: list[dict], cand: dict) -> tuple:
    """(coverage, inclusion, synergy|None, off_frac, hits) — mirrors score_commander."""
    edh = store.edhrec_for(cand["id"])
    ci = set(cand.get("color_identity") or [])
    n = len(deck_cards)
    hits, inc, syn, off = 0, 0.0, 0.0, 0
    for card in deck_cards:
        row = edh.get(card["id"])
        if row is not None:
            hits += 1
            syn += row[0] or 0.0
            inc += row[1] or 0.0
        if not set(card.get("color_identity") or []) <= ci:
            off += 1
    return (hits / n, inc / n, (syn / hits) if hits else None, off / n, hits)


def rank_of(target: str, cands: list[dict], w: tuple, exclude: str | None = None) -> float:
    """1-based rank of target under weights w, with find_pivots' exact sort key."""
    keyed = []
    for c in cands:
        if c["id"] == exclude:
            continue
        s = round(pivot.pivot_score(c["cov"], c["inc"], c["syn"], c["off"], w), 4)
        keyed.append(((-s, -c["hits"], -c["deck_count"], c["name"]), c["id"]))
    tkey = next((k for k, cid in keyed if cid == target), None)
    if tkey is None:
        return math.inf
    return 1 + sum(1 for k, _ in keyed if k < tkey)


def metrics_from_ranks(ranks: list[float]) -> dict:
    n = len(ranks)
    if not n:
        return {"n": 0}
    rr = [0.0 if math.isinf(r) else 1.0 / r for r in ranks]
    m = common.mean(rr)
    sd = math.sqrt(common.mean((x - m) ** 2 for x in rr))
    return {"n": n, "mrr": round(m, 4), "mrr_se": round(sd / math.sqrt(n), 4),
            "hit1": round(common.mean(r <= 1 for r in ranks), 4),
            "hit5": round(common.mean(r <= 5 for r in ranks), 4),
            "hit10": round(common.mean(r <= 10 for r in ranks), 4),
            "absent": sum(1 for r in ranks if math.isinf(r))}


def choose(train: dict[tuple, dict], train_full: dict[tuple, dict], current: tuple) -> tuple:
    """Pre-registered rule: among settings whose train FULL-deck MRR is no worse than the
    invented weights', take the best train PARTIAL-deck MRR; then (one-standard-error
    rule) the setting within 1 SE of it that is closest (L1) to the invented weights."""
    cap = train_full[current]["mrr"]
    ok = {w: s for w, s in train.items() if train_full[w]["mrr"] >= cap - 1e-12}
    best = max(ok, key=lambda w: (ok[w]["mrr"], -sum(abs(a - b) for a, b in zip(w, current))))
    floor = ok[best]["mrr"] - ok[best]["mrr_se"]
    near = [w for w, s in ok.items() if s["mrr"] >= floor]
    return min(near, key=lambda w: (sum(abs(a - b) for a, b in zip(w, current)), w))


def candidates_for(store, cached, ids: list[str]) -> tuple[list[dict], bool]:
    """All find_pivots candidates with raw components; bool = rescoring reproduces order."""
    out = pivot.find_pivots(cached, None, ids, limit=10 ** 6, include_all=True)
    deck_cards = pivot._deck_cards(store, ids, set())
    cands = []
    for c in out["candidates"]:
        cov, inc, syn, off, hits = components(store, deck_cards, c["commander"])
        assert hits == c["metrics"].hits
        assert round(pivot.pivot_score(cov, inc, syn, off), 4) == c["metrics"].score
        cands.append({"id": c["commander"]["id"], "name": c["commander"]["name"],
                      "deck_count": c["deck_count"], "hits": hits,
                      "cov": cov, "inc": inc, "syn": syn, "off": off})
    prod = [c["commander"]["id"] for c in out["candidates"]]
    mine = sorted(cands, key=lambda c: (-round(pivot.pivot_score(
        c["cov"], c["inc"], c["syn"], c["off"]), 4), -c["hits"], -c["deck_count"], c["name"]))
    return cands, [c["id"] for c in mine] == prod


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--decks", type=int, default=600)
    ap.add_argument("--seed", type=int, default=20261124)
    a = ap.parse_args()
    t0 = time.time()

    store, sizes = common.load_store()
    cached = common.CachedStore(store)
    corpus = common.load_corpus(store)
    decks = common.sample(corpus, a.decks, a.seed)
    corpus_sets = [(d["cmd_id"], frozenset(d["ids"]), d["deck_id"]) for d in corpus]

    cases = []
    mismatches = 0
    for d in decks:
        nonbasic = [cid for cid in d["ids"]
                    if "Basic" not in (store.get(cid).get("type_line") or "")]
        rng = common.rng_for(a.seed, d["deck_id"])
        part = sorted(rng.sample(nonbasic, min(PARTIAL_N, len(nonbasic))))
        full_c, ok1 = candidates_for(store, cached, d["ids"])
        part_c, ok2 = candidates_for(store, cached, part)
        mismatches += (not ok1) + (not ok2)

        # Nearest different-commander corpus deck (secondary ground truth).
        mine_set = frozenset(d["ids"])
        best_j, best_b = 0.0, None
        for cmd_id, s, deck_id in corpus_sets:
            if cmd_id == d["cmd_id"] or deck_id == d["deck_id"]:
                continue
            inter = len(mine_set & s)
            if not inter:
                continue
            j = inter / (len(mine_set) + len(s) - inter)
            if j > best_j:
                best_j, best_b = j, cmd_id
        cases.append({"deck": d, "full": full_c, "partial": part_c, "nn_j": best_j,
                      "nn_cmd": best_b if best_j >= NEIGHBOUR_J else None})
    if mismatches:
        raise SystemExit(f"rescoring disagrees with find_pivots on {mismatches} runs — fix first")
    n_train = sum(c["deck"]["split"] == "train" for c in cases)
    n_nb = sum(c["nn_cmd"] is not None for c in cases)
    print(f"{len(cases)} decks ({n_train} train / {len(cases) - n_train} held-out); "
          f"{n_nb} have a different-commander neighbour with Jaccard >= {NEIGHBOUR_J}; "
          f"rescoring reproduces find_pivots order on every run")

    def ranks(w, split, kind):
        out = []
        for c in cases:
            if c["deck"]["split"] != split:
                continue
            if kind in ("full", "partial"):
                out.append(rank_of(c["deck"]["cmd_id"], c[kind], w))
            elif c["nn_cmd"] is not None:
                out.append(rank_of(c["nn_cmd"], c["full"], w, exclude=c["deck"]["cmd_id"]))
        return out

    grid = sorted({(x, y, z, o) for x in GRID_COV for y in GRID_INC for z in GRID_SYN
                   for o in GRID_OFF if (x, y, z) != (0.0, 0.0, 0.0)} | {INVENTED})
    train_part = {w: metrics_from_ranks(ranks(w, "train", "partial")) for w in grid}
    train_full = {w: metrics_from_ranks(ranks(w, "train", "full")) for w in grid}
    chosen = choose(train_part, train_full, INVENTED)

    kinds = ("full", "partial", "nb")
    res, raw = {}, {}
    for name, w in (("invented", INVENTED), ("chosen", chosen),
                    ("coverage_only", (1.0, 0.0, 0.0, 0.0)),
                    ("inclusion_only", (0.0, 1.0, 0.0, 0.0))):
        for split in ("train", "test"):
            res[f"{split}:{name}"] = {"weights": w}
            for k in kinds:
                raw[(split, name, k)] = ranks(w, split, k)
                res[f"{split}:{name}"][k] = metrics_from_ranks(raw[(split, name, k)])

    def rr(rs):
        return [0.0 if math.isinf(r) else 1.0 / r for r in rs]

    boot = {}
    for k in kinds:
        boot[f"{k}_mrr_chosen_vs_invented"] = common.paired_bootstrap(
            rr(raw[("test", "invented", k)]), rr(raw[("test", "chosen", k)]), a.seed)
        boot[f"{k}_hit10_chosen_vs_invented"] = common.paired_bootstrap(
            [float(r <= 10) for r in raw[("test", "invented", k)]],
            [float(r <= 10) for r in raw[("test", "chosen", k)]], a.seed)
    mrrs = [s["mrr"] for s in train_part.values()]

    hdr = ["split", "setting", "w(cov,inc,syn,off)", "full MRR", "full h@1", "part MRR",
           "part h@1", "part h@10", "nb n", "nb MRR", "nb h@10"]
    rows = []
    for key, v in res.items():
        split, name = key.split(":")
        rows.append([split, name, ",".join(f"{x:g}" for x in v["weights"]), v["full"]["mrr"],
                     v["full"]["hit1"], v["partial"]["mrr"], v["partial"]["hit1"],
                     v["partial"]["hit10"], v["nb"]["n"], v["nb"].get("mrr", "-"),
                     v["nb"].get("hit10", "-")])
    print(common.table(rows, hdr))
    print(f"train partial-deck MRR across the {len(grid)}-point grid: "
          f"min {min(mrrs):.4f} max {max(mrrs):.4f}")
    print("\npaired bootstrap on held-out decks (chosen - invented, 95% CI):")
    for k, v in boot.items():
        if v["n"]:
            print(f"  {k}: {v['mean_diff']:+.4f}  [{v['ci95'][0]:+.4f}, {v['ci95'][1]:+.4f}]"
                  f"  n={v['n']}")
        else:
            print(f"  {k}: n=0")

    path = common.write_json("pivot.json", {
        "method": "own-commander recovery (full + partial deck) and nearest-neighbour "
                  "commander surfacing; see docs/plans/2026-11-24-ranking-eval.md",
        "seed": a.seed, "db": common.db_name(), "store_sizes": sizes,
        "params": {"decks_requested": a.decks, "neighbour_jaccard": NEIGHBOUR_J,
                   "partial_n": PARTIAL_N,
                   "grid": {"coverage": GRID_COV, "inclusion": GRID_INC, "synergy": GRID_SYN,
                            "off_color": GRID_OFF},
                   "per_commander_cap": common.PER_COMMANDER_CAP},
        "n_cases": len(cases), "n_neighbour_cases": n_nb, "invented": INVENTED,
        "chosen": chosen, "current_constants": pivot.WEIGHTS,
        "results": res, "bootstrap": boot,
        "train_grid": sorted(
            ({"weights": w, "partial": s, "full": train_full[w]} for w, s in train_part.items()),
            key=lambda r: -r["partial"]["mrr"]),
        "train_grid_partial_mrr_range": [min(mrrs), max(mrrs)],
        "neighbour_jaccard_distribution": sorted(round(c["nn_j"], 3) for c in cases),
        "elapsed_s": round(time.time() - t0, 1),
    })
    print(f"\nwrote {path}  ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
