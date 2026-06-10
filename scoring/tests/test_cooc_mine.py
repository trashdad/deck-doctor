import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cooccurrence.mine import deck_frequencies, mine_pairs  # noqa: E402


def test_deck_frequencies_counts_decks_containing_each_card():
    decks = [frozenset({"a", "b"}), frozenset({"a", "c"}), frozenset({"a"})]
    df = deck_frequencies(decks)
    assert df["a"] == 3
    assert df["b"] == 1


def test_mine_pairs_support_gate_and_lift():
    decks = [frozenset({"a", "b"})] * 4 + [frozenset({"a", "c"})]
    pairs = mine_pairs(decks, min_support=2)
    assert ("a", "b") in pairs
    assert ("a", "c") not in pairs
    ab = pairs[("a", "b")]
    assert ab["co_count"] == 4
    assert abs(ab["lift"] - 1.0) < 1e-9
    assert abs(ab["jaccard"] - 0.8) < 1e-9


def test_mine_pairs_keys_are_sorted():
    decks = [frozenset({"z", "a"})] * 3
    pairs = mine_pairs(decks, min_support=2)
    assert ("a", "z") in pairs
