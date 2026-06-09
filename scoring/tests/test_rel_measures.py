import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from relationships.measures import similarity  # noqa: E402


def test_identical_vectors_similarity_one():
    v = {"verb:DrawACard": 1, "kind:spell": 1}
    assert similarity(v, v) == 1.0


def test_disjoint_vectors_similarity_zero():
    assert similarity({"verb:DrawACard": 1}, {"verb:AddMana": 1}) == 0.0


def test_partial_overlap_between_zero_and_one():
    a = {"verb:AddMana": 1, "kind:activated": 1}
    b = {"verb:AddMana": 1, "kind:spell": 1}
    s = similarity(a, b)
    assert 0.0 < s < 1.0
