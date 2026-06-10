import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cooccurrence.edhrec import directional_synergy  # noqa: E402


def test_directional_synergy_clamps_to_unit_and_is_directional():
    rows = [("cmdr", "card", 0.62), ("cmdr", "neg", -0.3), ("cmdr", "big", 2.0)]
    syn = directional_synergy(rows)
    assert syn[("cmdr", "card")] == 0.62
    assert syn[("cmdr", "neg")] == 0.0
    assert syn[("cmdr", "big")] == 1.0
    assert ("card", "cmdr") not in syn


def test_directional_synergy_keeps_max_on_duplicate():
    rows = [("cmdr", "card", 0.3), ("cmdr", "card", 0.7)]
    syn = directional_synergy(rows)
    assert syn[("cmdr", "card")] == 0.7
