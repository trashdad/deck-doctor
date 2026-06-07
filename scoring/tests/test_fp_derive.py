import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fingerprints.schema import Amount, Effect, AbilityRecord  # noqa: E402
from fingerprints.derive import flat_tags  # noqa: E402


def _dmg(scope, quant, targeted):
    return AbilityRecord(ability_idx=0, kind="spell", effects=[Effect(
        verb="SpellDealsDamage", object="Creature", scope=scope,
        quantifier=quant, targeted=targeted, amount=Amount("literal", 13))])


def test_burn_each_vs_one_differ():
    each = flat_tags([_dmg("EachPermanent", "each", False)])
    one = flat_tags([_dmg("SinglePermanent", "single", True)])
    assert each != one
    assert "q:each" in each and "q:single" in one
    assert "tgts:targeted" in one and "tgts:targeted" not in each


def test_verb_maps_to_effect_tag():
    tags = flat_tags([_dmg("EachPermanent", "each", False)])
    assert "e:damage" in tags          # via ACTION_MAP[SpellDealsDamage]


def test_amount_bucket_present():
    tags = flat_tags([_dmg("EachPermanent", "each", False)])
    assert any(t.startswith("amt:") for t in tags)


from fingerprints.derive import build_inverted_index, fingerprint_to_vector  # noqa: E402


def test_inverted_index_groups_cards_by_tag():
    per_card = {"card_a": ["e:damage", "q:each"], "card_b": ["e:damage"]}
    idx = build_inverted_index(per_card)
    assert sorted(idx["e:damage"]) == ["card_a", "card_b"]
    assert idx["q:each"] == ["card_a"]


def test_fingerprint_to_vector_counts_axes():
    rec = AbilityRecord(ability_idx=0, kind="spell", effects=[Effect(
        verb="SpellDealsDamage", object="Creature", scope="EachPermanent",
        quantifier="each", targeted=False, amount=Amount("literal", 13))])
    vec = fingerprint_to_vector([rec])
    assert vec["kind:spell"] == 1
    assert vec["verb:SpellDealsDamage"] == 1
    assert vec["q:each"] == 1
    assert vec["targeted"] == 0


def test_static_keyword_tag_from_raw_rule():
    # Keyword-only abilities (e.g. Flying) are static records with no effects;
    # their tag must still be derived from the canonical raw _Rule op.
    rec = AbilityRecord(ability_idx=0, kind="static", raw={"_Rule": "Flying"})
    assert "k:flying" in flat_tags([rec])


def test_replacement_tag_from_raw_rule():
    rec = AbilityRecord(ability_idx=0, kind="replacement", raw={"_Rule": "ReplaceWouldDraw"})
    assert "r:replace_draw" in flat_tags([rec])


def test_vector_includes_static_keyword():
    rec = AbilityRecord(ability_idx=0, kind="static", raw={"_Rule": "Flying"})
    assert fingerprint_to_vector([rec]).get("k:flying") == 1


def test_counter_tag_from_effect():
    rec = AbilityRecord(ability_idx=0, kind="activated", effects=[Effect(
        verb="PutACounterOfTypeOnPermanent", counter="plus1")])
    assert "c:plus1" in flat_tags([rec])


def test_tgt_self_from_scope():
    rec = AbilityRecord(ability_idx=0, kind="spell", effects=[Effect(verb="DrawACard", scope="You")])
    assert "tgt:self" in flat_tags([rec])


def test_tgt_opponent_from_scope():
    rec = AbilityRecord(ability_idx=0, kind="spell", effects=[Effect(verb="LoseLife", scope="EachOpponent")])
    assert "tgt:opponent" in flat_tags([rec])
