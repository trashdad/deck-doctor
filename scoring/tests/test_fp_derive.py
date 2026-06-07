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
