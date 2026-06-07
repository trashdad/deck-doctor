import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fingerprints.schema import AbilityRecord, Effect, Amount  # noqa: E402
from fingerprints.qa import golden_diff, unmapped_operators  # noqa: E402


def test_golden_diff_match():
    rec = AbilityRecord(ability_idx=0, kind="spell",
                        effects=[Effect(verb="DrawACard")])
    assert golden_diff([rec], [rec.to_dict()]) == []


def test_golden_diff_mismatch_reports():
    a = AbilityRecord(ability_idx=0, kind="spell", effects=[Effect(verb="DrawACard")])
    b = AbilityRecord(ability_idx=0, kind="spell", effects=[Effect(verb="Scry")])
    diff = golden_diff([a], [b.to_dict()])
    assert diff and "ability_idx 0" in diff[0]


def test_unmapped_operators_lists_unknown():
    # ACTION_MAP knows DrawACard; "FrobnicateWidget" is invented/unknown
    cards = [{"Rules": [{"_Rule": "SpellActions", "args": [
        {"_Action": "DrawACard"}, {"_Action": "FrobnicateWidget"}]}]}]
    report = unmapped_operators(cards)
    names = {op for op, _count in report}
    assert "FrobnicateWidget" in names
    assert "DrawACard" not in names
