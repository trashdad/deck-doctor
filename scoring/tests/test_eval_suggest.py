"""SP10 eval harness tests."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scoring"))

import eval_suggest as ev  # noqa: E402


def test_split_stable():
    ids = ["archidekt:123", "moxfield:abc", "edhrec:foo", "x:y:z"]
    for did in ids:
        assert ev.split_of(did) == ev.split_of(did)        # stable
    # crc32-based, not salted hash — value is reproducible across processes
    assert ev.split_of("archidekt:123") in ("train", "test")


def test_holdout_deterministic():
    cands = [f"c{i}" for i in range(40)]
    a = ev.pick_holdout("deck-7", cands, 10)
    b = ev.pick_holdout("deck-7", cands, 10)
    assert a == b and len(a) == 10
    assert ev.pick_holdout("deck-8", cands, 10) != a or len(cands) < 10


def test_metrics_math():
    ranked = ["a", "b", "c", "d", "e"]
    # hit at rank 1 and rank 3
    H = {"a", "c"}
    assert ev.recall_at_k(ranked, H, 1) == 0.5          # only 'a' in top1
    assert ev.recall_at_k(ranked, H, 3) == 1.0          # both in top3
    assert ev.recall_at_k(ranked, H, 5) == 1.0
    # MRR = mean(1/1, 1/3) = (1 + 0.3333)/2
    assert abs(ev.mrr(ranked, H) - (1.0 + 1.0 / 3) / 2) < 1e-9
    # total miss
    assert ev.recall_at_k(ranked, {"z"}, 5) == 0.0
    assert ev.mrr(ranked, {"z"}) == 0.0


def test_runs_end_to_end_small():
    store = ev.get_store()
    decks = ev.load_decks(ROOT / "data" / "decks.sqlite")
    agg = ev.run_eval(store, decks, "all", holdout=10, limit=50, max_decks=5)
    assert agg["n_decks"] == 5
    for k in ("r10", "r25", "r50", "mrr"):
        assert 0.0 <= agg[k] <= 1.0
