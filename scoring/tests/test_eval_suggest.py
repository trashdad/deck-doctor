"""SP10 eval harness tests.

SCAFFOLD — remove the skip and implement per roadmap §10.3.
"""

import pytest

pytestmark = pytest.mark.skip(reason="SP10 scaffold — implement per roadmap §10.3")


def test_split_stable():
    """zlib.crc32-based split: the same deck_id maps to the same train/test bucket on
    every call and across processes (no salted hash())."""


def test_holdout_deterministic():
    """random.Random(deck_id) holdout: same deck → identical hidden set twice."""


def test_metrics_math():
    """Synthetic suggestions S and hidden H with known overlap → recall@k and MRR equal
    hand-computed values (cover: hit at rank 1, hit at rank k, total miss)."""


def test_runs_end_to_end_small():
    """--max-decks 5 completes, writes data/eval_results.json with n_decks == 5 and every
    recall value in [0, 1]."""
