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


from fingerprints.project import parse_scope  # noqa: E402


def test_scope_each_permanent():
    node = {"_DamageRecipient": "EachPermanent",
            "args": {"_Permanents": "IsCardtype", "args": "Creature"}}
    sc = parse_scope(node)
    assert sc["scope"] == "EachPermanent"
    assert sc["object"] == "Creature"
    assert sc["quantifier"] == "each"


def test_scope_single_permanent():
    node = {"_Permanents": "SinglePermanent", "args": {"_Permanent": "ThisPermanent"}}
    assert parse_scope(node)["quantifier"] == "single"


def test_scope_player_opponent():
    node = {"_Players": "Opponent"}
    sc = parse_scope(node)
    assert sc["scope"] == "Opponent" and sc["object"] == "player"


from fingerprints.project import extract_effects  # noqa: E402


def test_extract_simple_damage_each_creature():
    # Blasphemous Act body: SpellDealsDamage 13 to EachPermanent(Creature)
    actions = [{
        "_Action": "SpellDealsDamage",
        "args": [
            {"_Spell": "ThisSpell"},
            {"_GameNumber": "Integer", "args": 13},
            {"_DamageRecipient": "EachPermanent",
             "args": {"_Permanents": "IsCardtype", "args": "Creature"}},
        ],
    }]
    effs = extract_effects(actions)
    assert len(effs) == 1
    e = effs[0]
    assert e.verb == "SpellDealsDamage"
    assert e.object == "Creature" and e.quantifier == "each"
    assert e.amount.value == 13 and e.targeted is False


def test_extract_may_sets_optional():
    actions = [{"_Action": "MayAction",
                "args": {"_Action": "DrawACard"}}]
    effs = extract_effects(actions)
    assert len(effs) == 1
    assert effs[0].verb == "DrawACard" and effs[0].optional is True


def test_extract_targeted_flag():
    # Cruel Edict body: Targeted wrapper -> PlayerAction -> SacrificeAPermanent
    actions = [{
        "_Actions": "Targeted",
        "args": [
            [{"_Target": "TargetPlayer", "args": {"_Players": "Opponent"}}],
            {"_Actions": "ActionList", "args": [
                {"_Action": "PlayerAction", "args": [
                    {"_Player": "Ref_TargetPlayer"},
                    {"_Action": "SacrificeAPermanent",
                     "args": {"_Permanents": "IsCardtype", "args": "Creature"}},
                ]},
            ]},
        ],
    }]
    effs = extract_effects(actions)
    verbs = {e.verb for e in effs}
    assert "SacrificeAPermanent" in verbs
    assert any(e.targeted for e in effs)
