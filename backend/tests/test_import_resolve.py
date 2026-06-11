"""TDD tests for parse_decklist_rich and POST /deck/parse-import.

Covers:
- Clean Moxfield-style list resolves all cards + finds the commander.
- Misspelled card ("Sol Rng") lands under unresolved with Sol Ring in suggestions.
- Basic land quantities are preserved (not clamped to 1).
- (SET) 123 *F* suffixes are stripped before lookup.
- Bad input (empty string, whitespace-only) returns empty results, not an error.
- The HTTP endpoint returns full Card objects for resolved + unresolved suggestions.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.store import get_store
from app.importer import parse_decklist_rich

client = TestClient(app)
store = get_store()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _name_to_id(name: str) -> str:
    cid = store._name_to_id.get(name.lower())
    assert cid is not None, f"{name!r} not in store"
    return cid


def _card_name(cid: str) -> str:
    card = store.get(cid)
    assert card, f"card {cid} not found"
    return card["name"]


# ---------------------------------------------------------------------------
# Unit tests: parse_decklist_rich
# ---------------------------------------------------------------------------

class TestParseDecklistRich:
    def test_clean_moxfield_list_resolves_all(self):
        text = (
            "Commander: Sol Ring\n"   # forced-commander via prefix (unusual but valid)
            "1 Command Tower\n"
            "1 Lightning Bolt\n"
        )
        result = parse_decklist_rich(store, text)
        # All three should resolve
        assert len(result["unresolved"]) == 0, f"unexpected unresolved: {result['unresolved']}"
        resolved_names = {_card_name(r["card_id"]) for r in result["resolved"]}
        assert "Command Tower" in resolved_names
        assert "Lightning Bolt" in resolved_names

    def test_commander_marker_sets_commander_id(self):
        sr_id = _name_to_id("Sol Ring")
        text = f"Commander: Sol Ring\n1 Command Tower\n"
        result = parse_decklist_rich(store, text)
        # Sol Ring isn't a Legendary Creature but is explicitly flagged here
        assert result["commander_id"] == sr_id

    def test_legendary_creature_auto_promoted(self):
        """First Legendary Creature in list is auto-promoted to commander."""
        # Find any legendary creature in the store
        legend_id = None
        for cid, card in store._cards.items():
            if "Legendary Creature" in (card.get("type_line") or ""):
                legend_id = cid
                break
        assert legend_id is not None, "no Legendary Creature in store"
        legend_name = store.get(legend_id)["name"]
        text = f"1 {legend_name}\n1 Sol Ring\n"
        result = parse_decklist_rich(store, text)
        assert result["commander_id"] == legend_id

    def test_misspelled_card_in_unresolved_with_suggestions(self):
        """'Sol Rng' should be unresolved with Sol Ring in suggestions."""
        text = "1 Sol Rng\n"
        result = parse_decklist_rich(store, text)
        assert len(result["unresolved"]) == 1
        entry = result["unresolved"][0]
        assert entry["name"] == "Sol Rng"
        assert entry["quantity"] == 1
        suggestion_names = [_card_name(sid) for sid in entry["suggestion_ids"]]
        assert "Sol Ring" in suggestion_names, f"Sol Ring not in suggestions: {suggestion_names}"

    def test_unresolved_preserves_original_line(self):
        raw_line = "1 Sol Rng"
        result = parse_decklist_rich(store, raw_line)
        entry = result["unresolved"][0]
        assert entry["line"] == raw_line

    def test_basic_land_quantity_preserved(self):
        """Basics should sum their quantities, not clamp to 1."""
        text = "37 Forest\n"
        result = parse_decklist_rich(store, text)
        forest_rows = [r for r in result["resolved"]
                       if "Forest" in _card_name(r["card_id"])]
        assert forest_rows, "Forest not resolved"
        assert forest_rows[0]["quantity"] == 37

    def test_set_code_suffix_stripped(self):
        """'1 Sol Ring (C21) 263 *F*' should resolve to Sol Ring."""
        text = "1 Sol Ring (C21) 263 *F*\n"
        result = parse_decklist_rich(store, text)
        assert len(result["unresolved"]) == 0
        assert any(_card_name(r["card_id"]) == "Sol Ring" for r in result["resolved"])

    def test_empty_string_returns_empty(self):
        result = parse_decklist_rich(store, "")
        assert result == {"resolved": [], "unresolved": [], "commander_id": None}

    def test_whitespace_only_returns_empty(self):
        result = parse_decklist_rich(store, "   \n  \t  \n")
        assert result["resolved"] == []
        assert result["unresolved"] == []

    def test_comment_lines_ignored(self):
        text = "// This is a comment\n# Also a comment\n1 Sol Ring\n"
        result = parse_decklist_rich(store, text)
        assert len(result["unresolved"]) == 0
        assert any(_card_name(r["card_id"]) == "Sol Ring" for r in result["resolved"])

    def test_sideboard_lines_skipped(self):
        text = "1 Sol Ring\nSideboard\n1 Lightning Bolt\n"
        result = parse_decklist_rich(store, text)
        names = {_card_name(r["card_id"]) for r in result["resolved"]}
        assert "Sol Ring" in names
        assert "Lightning Bolt" not in names

    def test_cmdr_suffix_marker(self):
        """'1 Sol Ring *CMDR*' sets commander_id."""
        sr_id = _name_to_id("Sol Ring")
        text = "1 Sol Ring *CMDR*\n"
        result = parse_decklist_rich(store, text)
        assert result["commander_id"] == sr_id

    def test_nonbasic_quantity_clamped_to_1(self):
        text = "4 Sol Ring\n"
        result = parse_decklist_rich(store, text)
        sr_rows = [r for r in result["resolved"] if _card_name(r["card_id"]) == "Sol Ring"]
        assert sr_rows and sr_rows[0]["quantity"] == 1

    def test_up_to_5_suggestions(self):
        """Suggestions list has at most 5 entries."""
        text = "1 Lighning Blt\n"  # nonsense typo; suggestions may be 0–5
        result = parse_decklist_rich(store, text)
        for entry in result["unresolved"]:
            assert len(entry["suggestion_ids"]) <= 5


# ---------------------------------------------------------------------------
# Integration tests: POST /deck/parse-import
# ---------------------------------------------------------------------------

class TestParseImportEndpoint:
    def test_empty_text_returns_empty(self):
        r = client.post("/deck/parse-import", json={"text": ""})
        assert r.status_code == 200
        body = r.json()
        assert body["resolved"] == []
        assert body["unresolved"] == []
        assert body["commander_id"] is None

    def test_resolved_card_has_full_card_object(self):
        r = client.post("/deck/parse-import", json={"text": "1 Sol Ring\n"})
        assert r.status_code == 200
        body = r.json()
        assert len(body["resolved"]) == 1
        card = body["resolved"][0]["card"]
        assert card["name"] == "Sol Ring"
        # Full card object has required fields
        assert "id" in card
        assert "type_line" in card

    def test_unresolved_has_suggestions_with_full_cards(self):
        r = client.post("/deck/parse-import", json={"text": "1 Sol Rng\n"})
        assert r.status_code == 200
        body = r.json()
        assert len(body["unresolved"]) == 1
        entry = body["unresolved"][0]
        assert entry["name"] == "Sol Rng"
        assert entry["quantity"] == 1
        suggestion_names = [s["name"] for s in entry["suggestions"]]
        assert "Sol Ring" in suggestion_names

    def test_commander_id_in_response(self):
        sr_id = _name_to_id("Sol Ring")
        r = client.post("/deck/parse-import",
                        json={"text": "Commander: Sol Ring\n1 Command Tower\n"})
        assert r.status_code == 200
        assert r.json()["commander_id"] == sr_id

    def test_basic_quantity_preserved_via_endpoint(self):
        r = client.post("/deck/parse-import", json={"text": "20 Forest\n"})
        assert r.status_code == 200
        forest = [c for c in r.json()["resolved"]
                  if "Forest" in c["card"]["name"]]
        assert forest and forest[0]["quantity"] == 20

    def test_no_auth_required(self):
        """Endpoint must not require authentication (like /deck/complete)."""
        # TestClient doesn't send a session cookie by default
        r = client.post("/deck/parse-import", json={"text": "1 Sol Ring\n"})
        assert r.status_code == 200  # not 401/403
