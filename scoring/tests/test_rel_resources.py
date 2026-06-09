import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fingerprints.schema import AbilityRecord, Effect  # noqa: E402
from relationships.resources import card_resources, resource_match  # noqa: E402


def test_token_producer_produces_token():
    rec = AbilityRecord(ability_idx=0, kind="spell",
                        effects=[Effect(verb="CreateTokens")])
    res = card_resources([rec])
    assert "token" in res["produces"]


def test_dies_trigger_consumes_death_event():
    rec = AbilityRecord(ability_idx=0, kind="triggered",
                        trigger={"op": "WhenACreatureOrPlaneswalkerDies"},
                        effects=[Effect(verb="LoseLife")])
    res = card_resources([rec])
    assert "death_event" in res["consumes"]


def test_sac_outlet_produces_death_and_consumes_fodder():
    rec = AbilityRecord(ability_idx=0, kind="activated",
                        cost={"sacrifice": True},
                        effects=[Effect(verb="DrawACard")])
    res = card_resources([rec])
    assert "death_event" in res["produces"]
    assert "sacrifice_fodder" in res["consumes"]


def test_tap_cost_consumes_untap():
    rec = AbilityRecord(ability_idx=0, kind="activated",
                        cost={"tap": True}, effects=[Effect(verb="AddMana")])
    res = card_resources([rec])
    assert "untap" in res["consumes"]
    assert "mana" in res["produces"]


def test_counter_producer_and_generic_match():
    rec = AbilityRecord(ability_idx=0, kind="activated",
                        effects=[Effect(verb="PutACounterOfTypeOnPermanent", counter="plus1")])
    res = card_resources([rec])
    assert "counter:+1/+1" in res["produces"]
    assert resource_match("counter:+1/+1", "counter")
    assert resource_match("mana", "mana")
    assert not resource_match("mana", "token")
