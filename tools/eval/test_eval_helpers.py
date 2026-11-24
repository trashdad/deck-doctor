"""Pure-helper tests for the ranking backtests (no DB, no corpus).

Run: cd backend && DATABASE_URL=postgresql://x@localhost/deckdoctor_test \
         python -m pytest -q ../tools/eval/test_eval_helpers.py
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import backtest_cuts as bc  # noqa: E402
import backtest_pivot as bp  # noqa: E402
import common  # noqa: E402


def test_split_is_stable_and_commander_level():
    assert common.split_of("Atraxa, Praetors' Voice") == common.split_of("Atraxa, Praetors' Voice")
    names = [f"Commander {i}" for i in range(2000)]
    share = sum(common.split_of(n) == "train" for n in names) / len(names)
    assert 0.65 < share < 0.75


def test_paired_bootstrap_zero_and_positive_shift():
    same = common.paired_bootstrap([0.1, 0.2, 0.3], [0.1, 0.2, 0.3], seed=1)
    assert same["mean_diff"] == 0.0 and same["ci95"] == [0.0, 0.0]
    up = common.paired_bootstrap([0.0] * 50, [1.0] * 50, seed=1)
    assert up["mean_diff"] == 1.0 and up["ci95"][0] == 1.0


def _cand(cid, name, cov, hits=1, deck_count=0):
    return {"id": cid, "name": name, "cov": cov, "inc": 0.0, "syn": None, "off": 0.0,
            "hits": hits, "deck_count": deck_count}


def test_rank_of_uses_find_pivots_tiebreak_and_exclusion():
    w = (1.0, 0.0, 0.0, 0.0)
    cands = [_cand("a", "Alpha", 0.5, hits=3), _cand("b", "Beta", 0.5, hits=5),
             _cand("c", "Gamma", 0.9)]
    assert bp.rank_of("c", cands, w) == 1
    assert bp.rank_of("b", cands, w) == 2          # equal score, more hits wins
    assert bp.rank_of("a", cands, w) == 3
    assert bp.rank_of("a", cands, w, exclude="c") == 2
    assert math.isinf(bp.rank_of("zzz", cands, w))


def test_cut_choice_rule_respects_damage_cap_and_one_se_rule():
    cur = (0.15, 0.10)
    train = {
        cur: {"recall": 0.33, "recall_se": 0.02, "damage_0.5": 0.01},
        (0.10, 0.0): {"recall": 0.40, "recall_se": 0.02, "damage_0.5": 0.05},  # cuts staples
        (0.20, 0.10): {"recall": 0.34, "recall_se": 0.02, "damage_0.5": 0.01},
    }
    # (0.10, 0) is best on recall but breaks the damage cap; (0.20, 0.10) is within
    # 1 SE of the best admissible setting, so the current weights are kept.
    assert bc.choose(train, cur) == cur
    train[(0.20, 0.10)]["recall"] = 0.40
    assert bc.choose(train, cur) == (0.20, 0.10)


def test_pivot_choice_rule_needs_full_deck_no_worse():
    cur = (0.5, 0.3, 0.2, 1.0)
    part = {cur: {"mrr": 0.80, "mrr_se": 0.01}, (1.0, 0.0, 0.0, 1.0): {"mrr": 0.95, "mrr_se": 0.01},
            (0.5, 0.3, 0.0, 1.0): {"mrr": 0.85, "mrr_se": 0.01}}
    full = {cur: {"mrr": 0.90}, (1.0, 0.0, 0.0, 1.0): {"mrr": 0.80}, (0.5, 0.3, 0.0, 1.0): {"mrr": 0.91}}
    assert bp.choose(part, full, cur) == (0.5, 0.3, 0.0, 1.0)
