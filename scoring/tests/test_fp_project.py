import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fingerprints.project import parse_amount  # noqa: E402


def test_parse_amount_literal():
    node = {"_GameNumber": "Integer", "args": 13}
    a = parse_amount(node)
    assert a.kind == "literal" and a.value == 13


def test_parse_amount_dynamic():
    node = {"_GameNumber": "TheNumberOfPermanentsOnTheBattlefield",
            "args": {"_Permanents": "IsCardtype", "args": "Creature"}}
    a = parse_amount(node)
    assert a.kind == "dynamic"
    assert a.count["op"] == "TheNumberOfPermanentsOnTheBattlefield"
    assert a.count["counted_object"] == "Creature"


def test_parse_amount_none():
    assert parse_amount(None) is None
    assert parse_amount({"no_game_number": 1}) is None
