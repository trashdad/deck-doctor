"""SP7 test fixture — build a tiny synthetic spellbook.sqlite over REAL card names.

SCAFFOLD — implement per roadmap §7.7:

def make_spellbook_db(path: Path, store) -> dict:
    '''Create a spellbook.sqlite at `path` (schema = roadmap §7.2) containing:
      combo "fxA": 2 real cards sharing a color identity, produces ["Infinite mana"],
                   popularity 100
      combo "fxB": 3 real cards, produces ["Infinite draw"], popularity 50
      combo "fxC": 1 real card + "Nonexistent Card XYZ" (must be SKIPPED by
                   Store._load_spellbook because the name does not resolve)
    Pick the real names from store._cards deterministically (e.g. Sol Ring plus the first
    two colorless-identity artifacts by name) so tests can reference them.
    Returns {"a_members": [ids], "b_members": [ids]} for the tests to assert against.
    '''

Tests monkeypatch config.SPELLBOOK_PATH to this file and clear get_store's lru_cache
(see test_spellbook.py) so the Store reloads with the fixture combos.
"""
