import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cooccurrence.corpus import norm, decks_from_jsonl, edhrec_from_jsonl  # noqa: E402

SAMPLE = Path(__file__).resolve().parents[2] / "data" / "decklists" / "sample.jsonl"


def test_norm_folds_accents_and_case():
    assert norm("Atraxa, Praetors' Voice") == norm("atraxa, praetors' voice")
    assert norm("Lim-Dûl") == norm("Lim-Dul")


def test_decks_from_jsonl_returns_id_sets_dropping_unknowns():
    name_to_id = {norm(n): n.lower().replace(" ", "_") for n in
                  ["Sol Ring", "Arcane Signet", "Command Tower", "Lightning Bolt",
                   "Counterspell", "Doubling Season", "Goblin Chieftain",
                   "Evolution Sage", "Swords to Plowshares", "Cultivate"]}
    decks = decks_from_jsonl(SAMPLE, name_to_id)
    assert len(decks) == 10
    assert all(isinstance(d, frozenset) for d in decks)
    assert "sol_ring" in decks[0]
    assert all(cid in set(name_to_id.values()) for d in decks for cid in d)


def test_edhrec_from_jsonl_returns_commander_card_synergy():
    name_to_id = {norm(n): n.lower().replace(" ", "_") for n in
                  ["Atraxa, Praetors' Voice", "Doubling Season", "Evolution Sage",
                   "Sol Ring", "Krenko, Mob Boss", "Goblin Chieftain", "Lightning Bolt"]}
    rows = edhrec_from_jsonl(SAMPLE, name_to_id)
    assert ("atraxa,_praetors'_voice", "doubling_season", 0.62) in rows
    assert any(c == "krenko,_mob_boss" for c, _, _ in rows)
