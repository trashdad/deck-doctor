"""SP8 Deck Doctor tests (completion + cuts).

SCAFFOLD — remove the skip and implement per roadmap §8.6. Use the live store (real DBs),
resolve names via store._name_to_id like test_suggest.py does.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

pytestmark = pytest.mark.skip(reason="SP8 scaffold — implement per roadmap §8.6")


def test_complete_reaches_100_deterministic():
    """Ur-Dragon + 5 dragons → /deck/complete → final_size == 100; second call returns the
    IDENTICAL response; per-category counts within TEMPLATE ±1; zones are valid zone names."""


def test_complete_color_identity_and_banlist():
    """Mono-W EDHREC commander → every added card CI ⊆ {W}; nothing from BANLIST;
    basics are Plains only."""


def test_complete_respects_existing_surplus():
    """Seed 12 ramp cards → completion adds 0 further ramp and still reaches 100."""


def test_basics_follow_pips():
    """Heavy-R nonland seed under a WUBRG commander → Mountain count strictly greatest."""


def test_cuts_orders_low_contribution_first():
    """10 real Ur-Dragon signature dragons + 2 off-plan cards → both off-plan cards within
    the first 3 cuts; contributions ascending; commander and lands never present."""


def test_cuts_protects_complete_combos():
    """With the SP7 fixture loaded: a deck containing a complete fixture combo never lists
    its members as cuts."""
