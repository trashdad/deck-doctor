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


from relationships.measures import synergy  # noqa: E402


def test_synergy_directional_producer_to_consumer():
    a = {"produces": {"token"}, "consumes": set()}
    b = {"produces": set(), "consumes": {"token"}}
    ab, ba = synergy(a, b)
    assert ab > 0.0      # A makes tokens, B pays off tokens
    assert ba == 0.0     # B gives A nothing


def test_synergy_counter_generic_match():
    a = {"produces": {"counter:+1/+1"}, "consumes": set()}
    b = {"produces": set(), "consumes": {"counter"}}
    ab, ba = synergy(a, b)
    assert ab > 0.0


def test_synergy_none_when_no_resource_overlap():
    a = {"produces": {"mana"}, "consumes": set()}
    b = {"produces": set(), "consumes": {"token"}}
    assert synergy(a, b) == (0.0, 0.0)


from relationships.measures import anti_synergy  # noqa: E402


def test_anti_synergy_refill_vs_hellbent():
    # card A draws cards (refills hand); card B rewards empty hand
    a_tags = {"e:draw"}
    b_tags = {"cond:hellbent"}
    assert anti_synergy(a_tags, b_tags) > 0.0
    # order-independent
    assert anti_synergy(b_tags, a_tags) > 0.0


def test_anti_synergy_zero_for_unrelated():
    assert anti_synergy({"e:draw"}, {"e:mana"}) == 0.0
