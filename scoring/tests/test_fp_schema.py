import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fingerprints.schema import Amount, Effect, AbilityRecord  # noqa: E402


def test_amount_literal_roundtrip():
    a = Amount(kind="literal", value=13)
    assert Amount.from_dict(a.to_dict()) == a
    assert a.to_dict()["kind"] == "literal"


def test_amount_dynamic_roundtrip():
    a = Amount(kind="dynamic", count={"counted_object": "creature", "zone": "battlefield"})
    d = a.to_dict()
    assert d["count"]["counted_object"] == "creature"
    assert Amount.from_dict(d) == a


def test_ability_record_roundtrip():
    rec = AbilityRecord(
        ability_idx=0,
        kind="spell",
        effects=[Effect(verb="SpellDealsDamage", object="creature",
                        scope="EachPermanent", quantifier="each",
                        targeted=False, amount=Amount(kind="literal", value=13))],
        raw={"_Rule": "SpellActions"},
    )
    back = AbilityRecord.from_dict(rec.to_dict())
    assert back == rec
    assert back.effects[0].amount.value == 13
