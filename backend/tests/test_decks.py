"""SP6 deck persistence + import/export tests.

SCAFFOLD — remove the module-level skip and implement per roadmap §6.6
(docs/superpowers/plans/2026-06-10-sp6-sp11-roadmap.md). Each test's docstring is the spec.

Fixture requirements (write these first):
- autouse fixture `userdecks_tmp(tmp_path, monkeypatch)`:
    monkeypatch.setattr(config, "USERDECKS_PATH", tmp_path / "userdecks.sqlite")
    decks_module.get_userdecks.cache_clear()  # before AND after (yield) each test
  so every test gets a fresh file-backed DB and no test order coupling.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

pytestmark = pytest.mark.skip(reason="SP6 scaffold — implement per roadmap §6.6")


def test_crud_roundtrip():
    """POST deck (3 cards incl. commander) → list shows card_count 3 → GET detail resolves
    Card objects + zones → PUT with 4 cards → detail has 4 → DELETE 204 → GET 404."""


def test_import_formats():
    """One blob with: '1 Sol Ring', '1x Command Tower', bare 'Lightning Bolt',
    '1 Sol Ring (C21) 263 *F*' (dupe — must dedupe to 1), 'Commander: The Ur-Dragon',
    'SB: 1 Swords to Plowshares' (excluded), '## Lands' (ignored),
    '1 Totally Fake Card' (→ unresolved). Assert resolved ids, commander_id set,
    sideboard excluded, unresolved == exactly the fake line."""


def test_import_basics_quantity():
    """'8 Mountain' → quantity 8; '3 Sol Ring' → clamped to quantity 1 (singleton)."""


def test_export_roundtrip():
    """create → GET export (text/plain) → POST /decks/import with that text →
    identical (card_id, quantity) multiset, same commander_id, unresolved == []."""


def test_persistence_across_instances():
    """Save → get_userdecks.cache_clear() → new instance on same path still lists the deck."""
