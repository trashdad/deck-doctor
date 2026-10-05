"""Parser regression tests against captured source responses.

Fixtures are real responses fetched 2026-10-05 with the scraper's User-Agent.
User-identifying fields (owner, notes, description, panels, id tokens) are
removed. Card names and the fields the parsers read are unchanged.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRAPER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRAPER))

import runner  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"
FIELD_NAMES = {"cards", "commander", "commander_v2"}


def _load(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_archidekt_captured_deck_parses_real_cards():
    data = _load("archidekt_deck_27077380.json")
    commander, names = runner._parse_archidekt(data)
    assert commander == "Tidus, Yuna's Guardian"
    assert len(names) == 94
    assert "Sol Ring" in names
    assert "Arcane Signet" in names
    assert not (set(names) & FIELD_NAMES)


def test_archidekt_refuses_to_iterate_a_cards_dict():
    commander, names = runner._parse_archidekt({
        "categories": [],
        "cards": {"cards": [], "commander": [], "commander_v2": []},
    })
    assert commander is None
    assert names == []


def test_deckpreview_captured_object_parses_zones_not_keys():
    data = _load("edhrec_deckpreview_27071260.json")
    deck = data["deck"]
    # The bug: `for line in deck` walks these keys and stores them as cards.
    assert set(deck) == FIELD_NAMES

    parsed = runner._parse_edhrec_deckpreview(data)
    assert parsed is not None
    source, native_id, commander, names = parsed
    assert source == "archidekt"
    assert native_id == "27071260"
    assert commander == "Krenko, Mob Boss"
    assert len(names) == 75
    assert names[0] == "Krenko, Mob Boss"  # commander zone, once
    assert "Agate Instigator" in names
    assert "Altar of the Brood" in names
    assert "Cavern of Souls" in names
    assert "Collective Inferno" in names
    assert not (set(names) & FIELD_NAMES)
    assert len(names) == len(set(names))


def test_deckpreview_historical_line_list_still_parses():
    data = {
        "url": "https://moxfield.com/decks/ExamplePublicId",
        "commanders": ["Ghyrson Starn, Kelermorph"],
        "deck": [
            "1 Ghyrson Starn, Kelermorph",
            "1 Sol Ring",
            "12 Mountain",
        ],
    }
    source, native_id, commander, names = runner._parse_edhrec_deckpreview(data)
    assert source == "moxfield"
    assert native_id == "ExamplePublicId"
    assert commander == "Ghyrson Starn, Kelermorph"
    assert names == ["Ghyrson Starn, Kelermorph", "Sol Ring", "Mountain"]


def test_deckpreview_commander_fallback_reads_pair_shaped_zone():
    # No top-level `commanders`, and the commander zone uses the
    # [name, qty] pair shape that commander_v2 already uses.
    data = _load("edhrec_deckpreview_27071260.json")
    data.pop("commanders", None)
    data["deck"] = dict(data["deck"], commander=[["Krenko, Mob Boss", 1]])
    _source, _native_id, commander, names = runner._parse_edhrec_deckpreview(data)
    assert commander == "Krenko, Mob Boss"
    assert names[0] == "Krenko, Mob Boss"
