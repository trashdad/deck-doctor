"""SP7 Commander Spellbook integration tests.

SCAFFOLD — remove the skip and implement per roadmap §7.7. Tests must NOT require the real
spellbook download: build fixtures/spellbook_fixture.make_spellbook_db over real card names,
monkeypatch config.SPELLBOOK_PATH, and clear store.get_store's lru_cache around each test
(autouse fixture — restore + clear again on teardown so other test files see the real store).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

pytestmark = pytest.mark.skip(reason="SP7 scaffold — implement per roadmap §7.7")


def test_load_skips_unresolvable():
    """Fixture has 3 combos, one with a fake card name → len(store._spellbook) == 2."""


def test_deck_combos_complete_and_near():
    """Deck = both members of fxA + 1 member of fxB → POST /deck/combos:
    complete contains fxA; near contains fxB with the correct missing Card."""


def test_suggest_spellbook_completion():
    """Commander with CI ⊇ fxA identity; deck = all-but-one of fxA →
    /deck/recommend?explain=true contains the missing card with an 'engine' reason whose
    detail mentions 'Infinite mana', and engine bonus 1.2 outranks mined engines."""


def test_spellbook_endpoint_shapes():
    """GET /cards/{member}/spellbook-combos → fixture combos sorted popularity DESC with
    members resolved to Card objects; bogus card id → 404."""
