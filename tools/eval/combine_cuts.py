"""Combine the two cut-backtest regimes (played / legal intruders) on the TRAIN split.

The per-regime rule in backtest_cuts.py picks different weights in the two regimes,
so the final decision uses both: a setting is admissible if its train damage_0.5 is
within DAMAGE_TOL of the invented weights' in BOTH regimes. Admissible settings are
ranked by mean train recall@k over the two regimes. Held-out data is not read.

Usage: python -I tools/eval/combine_cuts.py   (after running backtest_cuts.py with
       --pool played and --pool legal)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

INVENTED = (0.15, 0.10)
DAMAGE_TOL = 0.002


def main() -> None:
    grids = {}
    for pool in ("played", "legal"):
        data = json.loads((common.RESULTS_DIR / f"cuts_{pool}.json").read_text(encoding="utf-8"))
        grids[pool] = {(r["role_w"], r["curve_w"]): r for r in data["train_grid"]}
    p, lg = grids["played"], grids["legal"]
    rows = []
    for w in sorted(p):
        ok = (p[w]["damage_0.5"] <= p[INVENTED]["damage_0.5"] + DAMAGE_TOL
              and lg[w]["damage_0.5"] <= lg[INVENTED]["damage_0.5"] + DAMAGE_TOL)
        rows.append({"role_w": w[0], "curve_w": w[1], "admissible": ok,
                     "mean_recall": round((p[w]["recall"] + lg[w]["recall"]) / 2, 4),
                     "recall_played": p[w]["recall"], "recall_legal": lg[w]["recall"],
                     "damage_played": p[w]["damage_0.5"], "damage_legal": lg[w]["damage_0.5"]})
    rows.sort(key=lambda r: -r["mean_recall"])
    adm = [r for r in rows if r["admissible"]]
    hdr = ["ROLE_W", "CURVE_W", "admissible", "mean rec", "rec played", "rec legal",
           "dmg played", "dmg legal"]
    print("TRAIN, both regimes, top 12 by mean recall@k (all settings):")
    print(common.table([[r["role_w"], r["curve_w"], r["admissible"], r["mean_recall"],
                         r["recall_played"], r["recall_legal"], r["damage_played"],
                         r["damage_legal"]] for r in rows[:12]], hdr))
    print("\nTRAIN, admissible (damage within %.3f of invented in both), top 6:" % DAMAGE_TOL)
    print(common.table([[r["role_w"], r["curve_w"], r["admissible"], r["mean_recall"],
                         r["recall_played"], r["recall_legal"], r["damage_played"],
                         r["damage_legal"]] for r in adm[:6]], hdr))
    inv = next(r for r in rows if (r["role_w"], r["curve_w"]) == INVENTED)
    print(f"\ninvented {INVENTED}: mean recall {inv['mean_recall']}; best admissible "
          f"({adm[0]['role_w']}, {adm[0]['curve_w']}) {adm[0]['mean_recall']} "
          f"(+{adm[0]['mean_recall'] - inv['mean_recall']:.4f})")
    path = common.RESULTS_DIR / "cuts_combined.json"
    path.write_text(json.dumps({"invented": INVENTED, "damage_tol": DAMAGE_TOL,
                                "rows": rows}, indent=2), encoding="utf-8")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
