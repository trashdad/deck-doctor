"""Backtest: does cut_to_100 find the cards that do not belong? (injected-intruder test)

Method (full write-up: docs/plans/2026-11-24-ranking-eval.md):
  1. Take real corpus decks (data/decks.sqlite, de-duplicated, <=5 per commander) as
     "good" 99s; basics are collapsed in the corpus, so pad back to 99 with basics of
     the commander's colours.
  2. Inject k in [3, 8] known-bad cards (seeded per deck). Every injected card is a
     real corpus-played card (non-land, in colour identity, not banned, not already in
     the deck) that < OFF_THEME_INCL of this commander's EDHREC decks run, of one of:
       random    — any such card;
       curve     — such a card with cmc >= 7 (off-curve top end);
       role_glut — such a card of a quota role the deck already fills (board wipe
                   first, i.e. "a 4th wipe"; else the most over-full role).
  3. Ask cut_to_100 for the k cuts (deck is now 99 + k + commander → over by k).
  4. recall@k = injected cards among the cuts / k. damaging@X = cuts of ORIGINAL cards
     that >= X of this commander's EDHREC decks run, / k.
  5. Grid-search ROLE_W x CURVE_W on the TRAIN commanders (70 %), choose with a
     pre-registered rule, then compare chosen vs current on the HELD-OUT commanders
     (30 %) with a paired bootstrap CI.

Usage (read-only; never point it at prod):
  DATABASE_URL=postgresql://deckdoctor@localhost/deckdoctor_test \
      python -I tools/eval/backtest_cuts.py [--decks 600] [--seed 20261124]
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

from app import cut_to_100 as c100  # noqa: E402
from app.doctor import TEMPLATE, category_of  # noqa: E402
from app.suggest import BANLIST  # noqa: E402

OFF_THEME_INCL = 0.10
DAMAGE_THRESHOLDS = (0.3, 0.5)
K_RANGE = (3, 8)
NOISE_TYPES = ("random", "curve", "role_glut")
GRID = (0.0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.50, 0.75, 1.00)
QUOTA_ROLES = ("board_wipe", "removal", "ramp", "card_draw")


SPELL_TYPES = ("Creature", "Instant", "Sorcery", "Artifact", "Enchantment", "Planeswalker",
               "Battle")


def build_pool(store, kind: str = "played") -> list[dict]:
    """Intruder candidates (canonical ids only, non-land, non-basic, not banned).

    played — cards that appear in the corpus co-occurrence table (store._staples):
             plausible cards somebody would actually slot in. Primary regime.
    legal  — any castable card in data/cards.json (robustness regime: most of these
             carry no corpus signal at all, exactly like a deck's obscure picks).
    """
    if kind == "played":
        ids = [cid for cid, _freq in store._staples]
    else:
        ids = sorted(store._cards)
    pool = []
    for cid in ids:
        card = store.get(cid)
        if card is None or card.get("name") in BANLIST:
            continue
        tl = card.get("type_line") or ""
        if kind == "legal" and ("Token" in tl or not any(t in tl for t in SPELL_TYPES)
                                or not card.get("mana_cost")):
            continue
        if store._name_to_id.get((card.get("name") or "").lower()) != cid:
            continue
        if category_of(card) == "land" or "Basic" in (card.get("type_line") or ""):
            continue
        pool.append(card)
    return pool


def inject(store, deck: dict, pool: list[dict], seed: int):
    """-> (deck_side ids incl. padding + injected, {injected_id: noise_type}) or None."""
    rng = common.rng_for(seed, deck["deck_id"])
    cmd = store.get(deck["cmd_id"])
    ci = set(cmd.get("color_identity") or [])
    edh = store.edhrec_for(deck["cmd_id"])
    present = set(deck["ids"]) | {deck["cmd_id"]}
    ok = [c for c in pool if c["id"] not in present
          and set(c.get("color_identity") or []) <= ci
          and edh.get(c["id"], (0.0, 0.0))[1] < OFF_THEME_INCL]
    if not ok:
        return None

    roles: dict[str, int] = {}
    for cid in deck["ids"]:
        cat = category_of(store.get(cid))
        roles[cat] = roles.get(cat, 0) + 1
    if roles.get("board_wipe", 0) >= TEMPLATE["board_wipe"]:
        glut_role = "board_wipe"
    else:
        glut_role = max(QUOTA_ROLES, key=lambda r: (roles.get(r, 0) / TEMPLATE[r], r))
    by_type = {
        "random": ok,
        "curve": [c for c in ok if float(c.get("cmc") or 0) >= 7],
        "role_glut": [c for c in ok if category_of(c) == glut_role],
    }

    basics = common.basic_ids(store, ci)
    side = list(deck["ids"])
    i = 0
    while len(side) < common.DECK_SIDE:
        side.append(basics[i % len(basics)])
        i += 1

    k = rng.randint(*K_RANGE)
    injected: dict[str, str] = {}
    for _ in range(k):
        t = rng.choice(NOISE_TYPES)
        cands = [c for c in by_type[t] if c["id"] not in injected]
        if not cands:   # e.g. no cmc >= 7 card in identity: fall back, labelled honestly
            t = "random"
            cands = [c for c in ok if c["id"] not in injected]
        if not cands:
            break
        injected[rng.choice(cands)["id"]] = t
    return side + list(injected), injected


def score_run(res: dict, injected: dict[str, str], edh: dict) -> dict:
    k = len(injected)
    cut_ids = [c["card_id"] for c in res["cuts"]]
    hit = set(cut_ids) & set(injected)
    row = {"k": k, "recall": len(hit) / k, "shortfall": res["shortfall"],
           "breaks_quota": sum(c["breaks_quota"] for c in res["cuts"]),
           "land_cuts": sum(c["role"] == "land" for c in res["cuts"])}
    for t in NOISE_TYPES:
        row[f"inj_{t}"] = sum(1 for v in injected.values() if v == t)
        row[f"hit_{t}"] = sum(1 for cid in hit if injected[cid] == t)
    for x in DAMAGE_THRESHOLDS:
        row[f"damage_{x}"] = sum(1 for cid in cut_ids if cid not in injected
                                 and edh.get(cid, (0.0, 0.0))[1] >= x) / k
    return row


def summarise(rows: list[dict]) -> dict:
    out = {"n_decks": len(rows), "recall": round(common.mean(r["recall"] for r in rows), 4)}
    sd = math.sqrt(common.mean((r["recall"] - out["recall"]) ** 2 for r in rows)) if rows else 0.0
    out["recall_se"] = round(sd / math.sqrt(len(rows)), 4) if rows else None
    for x in DAMAGE_THRESHOLDS:
        out[f"damage_{x}"] = round(common.mean(r[f"damage_{x}"] for r in rows), 4)
    for t in NOISE_TYPES:
        inj = sum(r[f"inj_{t}"] for r in rows)
        out[f"recall_{t}"] = round(sum(r[f"hit_{t}"] for r in rows) / inj, 4) if inj else None
    out["breaks_quota_per_deck"] = round(common.mean(r["breaks_quota"] for r in rows), 4)
    out["land_cuts_per_deck"] = round(common.mean(r["land_cuts"] for r in rows), 4)
    out["random_reference_recall"] = round(common.mean(r["k"] / (99 + r["k"]) for r in rows), 4)
    return out


def choose(train: dict[tuple, dict], current: tuple) -> tuple:
    """Pre-registered rule: among settings whose train damage_0.5 is no worse than the
    current setting's, take the best train recall; then (one-standard-error rule) the
    setting within 1 SE of it that is CLOSEST to the current weights."""
    cap = train[current]["damage_0.5"]
    ok = {w: s for w, s in train.items() if s["damage_0.5"] <= cap + 1e-12}
    best = max(ok, key=lambda w: (ok[w]["recall"], -abs(w[0] - current[0]) - abs(w[1] - current[1])))
    floor = ok[best]["recall"] - ok[best]["recall_se"]
    near = [w for w, s in ok.items() if s["recall"] >= floor]
    return min(near, key=lambda w: (abs(w[0] - current[0]) + abs(w[1] - current[1]), w))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--decks", type=int, default=600)
    ap.add_argument("--seed", type=int, default=20261124)
    ap.add_argument("--pool", choices=("played", "legal"), default="played")
    a = ap.parse_args()
    t0 = time.time()

    store, sizes = common.load_store()
    cached = common.CachedStore(store)
    memo: dict = {}
    real_suggest = c100.suggest_cuts

    def memo_suggest(st, cmd, deck, limit=10):
        key = (cmd, tuple(deck), limit)
        if key not in memo:
            memo[key] = real_suggest(st, cmd, deck, limit=limit)
        return memo[key]

    c100.suggest_cuts = memo_suggest   # weight-independent; cache it across the grid

    decks = common.sample(common.load_corpus(store), a.decks, a.seed)
    pool = build_pool(store, a.pool)
    cases = []
    for d in decks:
        inj = inject(store, d, pool, a.seed)
        if inj is None:
            continue
        side, injected = inj
        cases.append((d, side, injected, store.edhrec_for(d["cmd_id"])))
    print(f"{len(cases)} decks ({sum(c[0]['split'] == 'train' for c in cases)} train / "
          f"{sum(c[0]['split'] == 'test' for c in cases)} held-out), pool {len(pool)} cards")

    current = (c100.ROLE_W, c100.CURVE_W)
    settings = sorted({(rw, cw) for rw in GRID for cw in GRID} | {current, (0.15, 0.10)})
    per: dict[tuple, dict[str, list[dict]]] = {}
    for w in settings:
        per[w] = {"train": [], "test": []}
        for d, side, injected, edh in cases:
            res = c100.cut_to_100(cached, d["cmd_id"], side, role_w=w[0], curve_w=w[1])
            per[w][d["split"]].append(score_run(res, injected, edh))
    c100.suggest_cuts = real_suggest

    train = {w: summarise(per[w]["train"]) for w in settings}
    pre = (0.15, 0.10)          # the invented weights this eval set out to check
    chosen = choose(train, pre)
    pure = (0.0, 0.0)

    test = {name: summarise(per[w]["test"]) for name, w in
            (("invented_0.15_0.10", pre), ("pure_weakness_0_0", pure), ("chosen", chosen))}
    boot = {}
    for metric in ("recall", "damage_0.5", "damage_0.3"):
        boot[f"chosen_vs_invented_{metric}"] = common.paired_bootstrap(
            [r[metric] for r in per[pre]["test"]], [r[metric] for r in per[chosen]["test"]], a.seed)
        boot[f"invented_vs_pure_{metric}"] = common.paired_bootstrap(
            [r[metric] for r in per[pure]["test"]], [r[metric] for r in per[pre]["test"]], a.seed)
    train_recalls = [s["recall"] for s in train.values()]

    hdr = ["setting", "ROLE_W", "CURVE_W", "recall@k", "rec_random", "rec_curve",
           "rec_glut", "dmg>=0.5", "dmg>=0.3", "quota_breaks"]
    print("\nTRAIN (commanders in the 70 % split)")
    print(common.table([[n, w[0], w[1], train[w]["recall"], train[w]["recall_random"],
                         train[w]["recall_curve"], train[w]["recall_role_glut"],
                         train[w]["damage_0.5"], train[w]["damage_0.3"],
                         train[w]["breaks_quota_per_deck"]]
                        for n, w in (("invented", pre), ("pure", pure), ("chosen", chosen))], hdr))
    print(f"train recall over the whole {len(settings)}-point grid: "
          f"min {min(train_recalls):.4f} max {max(train_recalls):.4f}")
    print("\nHELD-OUT (commanders in the 30 % split)")
    print(common.table([[n, w[0], w[1], test[k]["recall"], test[k]["recall_random"],
                         test[k]["recall_curve"], test[k]["recall_role_glut"],
                         test[k]["damage_0.5"], test[k]["damage_0.3"],
                         test[k]["breaks_quota_per_deck"]]
                        for n, w, k in (("invented", pre, "invented_0.15_0.10"),
                                        ("pure", pure, "pure_weakness_0_0"),
                                        ("chosen", chosen, "chosen"))], hdr))
    print(f"random-cut reference recall: {test['chosen']['random_reference_recall']:.4f}")
    print("\npaired bootstrap on held-out decks (mean diff, 95% CI):")
    for k, v in boot.items():
        print(f"  {k}: {v['mean_diff']:+.4f}  [{v['ci95'][0]:+.4f}, {v['ci95'][1]:+.4f}]  n={v['n']}")

    path = common.write_json(f"cuts_{a.pool}.json", {
        "method": "injected-intruder recall@k; see docs/plans/2026-11-24-ranking-eval.md",
        "seed": a.seed, "db": common.db_name(), "store_sizes": sizes,
        "params": {"pool": a.pool, "decks_requested": a.decks, "k_range": K_RANGE, "off_theme_incl": OFF_THEME_INCL,
                   "noise_types": NOISE_TYPES, "grid": GRID, "pool_size": len(pool),
                   "per_commander_cap": common.PER_COMMANDER_CAP},
        "n_cases": len(cases), "current_constants": current, "invented": pre,
        "chosen": chosen,
        "train_grid": [{"role_w": w[0], "curve_w": w[1], **train[w]} for w in settings],
        "held_out": test, "bootstrap": boot,
        "elapsed_s": round(time.time() - t0, 1),
    })
    print(f"\nwrote {path}  ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
