"""build_semantics tags for the restructured upstream MTGish schema (i5jb/mtgish 153451e).

Every fixture entry is a real upstream card object (see the fixture's "source").
Card behaviour cited in comments is the card's Oracle text from data/cards.json.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build_semantics import ability_tag_lists  # noqa: E402
from mtgish_schema import load_mtgish  # noqa: E402
from tag_taxonomy import action_tags  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "mtgish_upstream_2026-10-07_port.json"
CARDS = {c["Name"]: c for c in json.loads(FIX.read_text(encoding="utf-8"))["cards"]}


def _sem(name: str, idx: int | None = None) -> set[str]:
    lists = ability_tag_lists(CARDS[name]["Rules"])
    if idx is not None:
        return set(lists[idx])
    return {t for ab in lists for t in ab}


def test_load_mtgish_reads_json_lines_and_json_arrays(tmp_path):
    cards = [CARDS["Coretapper"], CARDS["Prey Upon"]]
    lines = tmp_path / "mtgish.lines.json"
    lines.write_text("\n".join(json.dumps(c) for c in cards) + "\n", encoding="utf-8")
    array = tmp_path / "cards.json"
    array.write_text(json.dumps(cards), encoding="utf-8")
    assert [c["Name"] for c in load_mtgish(lines)] == ["Coretapper", "Prey Upon"]
    assert [c["Name"] for c in load_mtgish(array)] == ["Coretapper", "Prey Upon"]


def test_qualified_verbs_fall_back_to_the_plain_op():
    assert action_tags("PutCounters.NumberCountersOfTypeOnPermanent") == ["e:add_counter"]
    assert action_tags("Exile.TheTopCardOfLibrary") == ["e:exile"]
    assert action_tags("Reflexive_PayMana_Sacrifice_WhenYouDo") == ["e:sacrifice"]
    assert action_tags("Reflexive_PayMana_WhenYouDo") == []


def test_put_a_counter_on_each_keeps_the_legacy_proliferate_tag():
    # Cathars' Crusade: "Whenever a creature you control enters, put a +1/+1 counter
    # on each creature you control." The April op PutACounterOfTypeOnEachPermanent was
    # tagged e:add_counter + e:proliferate; the upstream variant keeps that mapping.
    assert {"e:add_counter", "e:proliferate", "c:plus1"} <= _sem("Cathars' Crusade")
    # Contractual Safeguard: "... Choose a kind of counter on a creature you control. Put a
    # counter of that kind on each other creature you control." (April: the same op)
    assert {"e:add_counter", "e:proliferate"} <= _sem("Contractual Safeguard")


def test_exile():
    # Swords to Plowshares: "Exile target creature. Its controller gains life equal to its power."
    assert "e:exile" in _sem("Swords to Plowshares")


def test_reflexive_steps_and_bodies():
    # Kishla Trawlers: "When this creature enters, you may exile a creature card from your
    # graveyard. When you do, return target instant or sorcery card from your graveyard
    # to your hand."
    assert {"e:exile", "e:reanimate", "t:etb"} <= _sem("Kishla Trawlers")
    # Curse of the Werefox: "Create a Monster Role token attached to target creature you
    # control. When you do, that creature fights up to one target creature you don't control. (...)"
    assert {"e:create_token", "e:fight"} <= _sem("Curse of the Werefox")
    # Skeleton Scavengers: "Pay {1} for each +1/+1 counter on this creature: Regenerate this
    # creature. When it regenerates this way, put a +1/+1 counter on it."
    assert {"e:regenerate", "e:add_counter"} <= _sem("Skeleton Scavengers", 1)


def test_fight():
    # Prey Upon: "Target creature you control fights target creature you don't control. (...)"
    assert "e:fight" in _sem("Prey Upon")


def test_prevent_damage_rule_is_a_damage_replacement():
    # Angel of Suffering: "If damage would be dealt to you, prevent that damage and mill
    # twice that many cards."
    assert "r:replace_damage" in _sem("Angel of Suffering", 1)
    # Phyrexian Vindicator: "If damage would be dealt to this creature, prevent that damage.
    # When damage is prevented this way, this creature deals that much damage to any other target."
    assert {"r:replace_damage", "e:damage"} <= _sem("Phyrexian Vindicator", 1)


def test_token_makers():
    # Elephant Resurgence: "Each player creates a green Elephant creature token. Those
    # creatures have ..."
    assert "e:create_token" in _sem("Elephant Resurgence")
    # Master of Ceremonies: "... you and that player each create a Treasure token ... each
    # create a 1/1 green and white Citizen creature token ... each draw a card."
    assert {"e:create_token", "e:draw"} <= _sem("Master of Ceremonies")


def test_ops_on_the_created_tokens_as_a_group():
    # Feldon of the Third Path: "... Create a token that's a copy of target creature card in
    # your graveyard ... It gains haste. Sacrifice it at the beginning of the next end step."
    # Upstream: TheTokensCreatedThisWay + CreateEachPermanentLayerEffect / SacrificeEachPermanent.
    assert {"e:create_token", "e:pump", "e:sacrifice", "k:haste"} <= _sem("Feldon of the Third Path")
    # Rolling Hamsphere: "... create three 1/1 red Hamster creature tokens, then it deals X damage
    # to any target ..." (upstream: EachPermanentDealsDamage)
    assert "e:damage" in _sem("Rolling Hamsphere", 1)
    # Cauldron Dance: "... Its controller sacrifices it at the beginning of the next end step."
    assert "e:sacrifice" in _sem("Cauldron Dance", 1)
    # Cut the Tethers: "For each Spirit, return it to its owner's hand unless that player pays {3}."
    assert "e:bounce" in _sem("Cut the Tethers")


def test_counter_placed_trigger_upstream_name():
    # Hollowmurk Siege: "• Sultai — Whenever a counter is put on a creature you control, draw a
    # card. This ability triggers only once each turn."
    assert {"t:counter_placed", "e:draw"} <= _sem("Hollowmurk Siege", 1)


def test_look_at_top_new():
    # Gilgamesh, Master-at-Arms: "Whenever Gilgamesh enters or attacks, look at the top six cards
    # of your library. ..."
    assert "e:scry" in _sem("Gilgamesh, Master-at-Arms")


def test_semantics_reach_keywords_granted_by_tokens():
    # Rekindling Phoenix: "When this creature dies, create a 0/1 red Elemental creature token with
    # "At the beginning of your upkeep, sacrifice this token and return target card named
    # Rekindling Phoenix ... It gains haste until end of turn."" -- one level deeper upstream.
    assert {"k:haste", "e:reanimate", "e:sacrifice"} <= _sem("Rekindling Phoenix", 1)
