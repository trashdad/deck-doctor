"""Fingerprints (projector, derived tags, resources) for the restructured upstream
MTGish schema (i5jb/mtgish 153451e). build_semantics tags: test_mtgish_port_tags.py.

Every fixture entry is a real upstream card object (see the fixture's "source").
Card behaviour cited in comments is the card's Oracle text from data/cards.json.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fingerprints.project import project_card  # noqa: E402
from fingerprints.derive import flat_tags, fingerprint_to_vector  # noqa: E402
from relationships.resources import card_resources  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "mtgish_upstream_2026-10-07_port.json"
CARDS = {c["Name"]: c for c in json.loads(FIX.read_text(encoding="utf-8"))["cards"]}


def _recs(name: str):
    return project_card(CARDS[name])


def _flat(name: str, idx: int | None = None) -> set[str]:
    recs = _recs(name)
    return set(flat_tags([recs[idx]] if idx is not None else recs))


def _verbs(rec) -> list[str]:
    return [e.verb for e in rec.effects]


# ── counters: PutCounters + _PutCountersAction ───────────────────────────────

def test_put_counters_verb_keeps_the_variant_and_reads_the_nested_amount():
    # Coretapper: "Sacrifice this creature: Put two charge counters on target artifact."
    rec = _recs("Coretapper")[1]
    (e,) = rec.effects
    assert e.verb == "PutCounters.NumberCountersOfTypeOnPermanent"
    assert e.counter == "charge"
    assert e.amount is not None and e.amount.kind == "literal" and e.amount.value == 2
    assert {"e:add_counter", "c:charge", "amt:mid"} <= _flat("Coretapper", 1)


def test_put_a_counter_on_each_keeps_the_legacy_proliferate_tag():
    # Cathars' Crusade: "Whenever a creature you control enters, put a +1/+1 counter
    # on each creature you control." The April op PutACounterOfTypeOnEachPermanent was
    # tagged e:add_counter + e:proliferate; the upstream variant keeps that mapping.
    (rec,) = _recs("Cathars' Crusade")
    (e,) = rec.effects
    assert e.verb == "PutCounters.ACounterOfTypeOnEachPermanent"
    assert e.object == "Creature" and e.counter == "plus1"
    assert {"e:add_counter", "e:proliferate", "c:plus1", "perm:creature"} <= _flat("Cathars' Crusade")


def test_put_counters_with_several_variants_yields_one_effect_each():
    # Abigale, Eloquent First-Year: "When Abigale enters, up to one other target creature
    # loses all abilities. Put a flying counter, a first strike counter, and a lifelink
    # counter on that creature."
    rec = _recs("Abigale, Eloquent First-Year")[3]
    assert _verbs(rec).count("PutCounters.ACounterOfTypeOnPermanent") == 3


def test_vector_uses_the_qualified_verb():
    vec = fingerprint_to_vector(_recs("Coretapper"))
    assert vec["verb:PutCounters.ACounterOfTypeOnPermanent"] == 1
    assert vec["verb:PutCounters.NumberCountersOfTypeOnPermanent"] == 1


def test_removing_counters_does_not_count_as_producing_them():
    # Amy Pond: "Whenever Amy Pond deals combat damage to a player, choose a suspended
    # card you own and remove that many time counters from it."
    recs = _recs("Amy Pond")
    removes = [e for r in recs for e in r.effects if e.verb.startswith("RemoveCounters")]
    assert [e.verb for e in removes] == ["RemoveCounters.NumberCountersOfTypeFromACardInExile"]
    assert removes[0].counter == "time"
    produced = card_resources(recs)["produces"]
    assert "counter" not in produced
    assert "counter:time" not in produced
    # Coretapper: "Sacrifice this creature: Put two charge counters on target artifact."
    placed = card_resources(_recs("Coretapper"))["produces"]
    assert "counter" in placed and "counter:charge" in placed


def test_delayed_counter_removal_does_not_produce_counters():
    # Clockwork Beetle: "Whenever this creature attacks or blocks, remove a +1/+1
    # counter from it at end of combat."
    recs = _recs("Clockwork Beetle")
    delayed = [e for r in recs for e in r.effects if e.verb == "CreateFutureTrigger"]
    assert [s.verb for e in delayed for s in e.sub_effects] == [
        "RemoveCounters.ACounterOfTypeFromPermanent",
        "RemoveCounters.ACounterOfTypeFromPermanent",
    ]
    assert all(s.counter == "plus1" for e in delayed for s in e.sub_effects)
    produced = card_resources(recs)["produces"]
    assert "counter" not in produced and "counter:+1/+1" not in produced
    assert "c:plus1" in _flat("Clockwork Beetle", 1)
    assert "e:remove_counter" in _flat("Clockwork Beetle", 1)


def test_delayed_trigger_inside_a_may_wrapper_stays_optional():
    # Meek Attack: "{1}{R}: You may put a creature card with total power and toughness 5 or
    # less from your hand onto the battlefield. That creature gains haste. At the beginning of
    # the next end step, sacrifice that creature." (all under one MayActions)
    (rec,) = _recs("Meek Attack")
    assert _verbs(rec) == ["PutACardFromHandOnBattlefield", "CreatePermanentLayerEffect",
                           "CreateFutureTrigger"]
    assert all(e.optional for e in rec.effects)
    assert rec.optional is True
    assert all(s.optional for s in rec.effects[2].sub_effects)


def test_choose_an_action_wrapper_leaves_counters_to_its_options():
    # Jinxed Choker: "{3}: Put a charge counter on this artifact or remove one from it."
    # The options are projected as their own effects; the ChooseAnAction wrapper must not
    # copy one option's counter (it would claim the removal option places it).
    rec = _recs("Jinxed Choker")[2]
    assert _verbs(rec) == ["ChooseAnAction", "PutCounters.ACounterOfTypeOnPermanent",
                           "RemoveCounters.ACounterOfTypeFromPermanent"]
    assert rec.effects[0].counter is None
    assert [e.counter for e in rec.effects[1:]] == ["charge", "charge"]
    assert {"c:charge", "e:add_counter", "e:remove_counter"} <= _flat("Jinxed Choker", 2)


def test_counter_removal_cost_inside_an_action_is_not_a_counter_product():
    # Woeleecher: "{W}, {T}: Remove a -1/-1 counter from target creature. If you do, you
    # gain 2 life." (upstream: MustCost {_Cost RemoveCounters}, If CostWasPaid GainLife)
    (rec,) = _recs("Woeleecher")
    must = rec.effects[0]
    assert must.verb == "MustCost" and must.counter is None
    assert [(s.verb, s.counter) for s in must.sub_effects] == [
        ("RemoveCounters.ACounterOfTypeFromPermanent", "minus1")]
    produced = card_resources([rec])["produces"]
    assert "counter" not in produced and "counter:-1/-1" not in produced
    assert {"c:minus1", "e:remove_counter", "e:gain_life"} <= _flat("Woeleecher")
    # Noosegraf Mob: "Whenever a player casts a spell, remove a +1/+1 counter from this
    # creature. If you do, create a 2/2 black Zombie creature token."
    produced = card_resources(_recs("Noosegraf Mob"))["produces"]
    assert "token" in produced
    assert "counter" not in produced and "counter:+1/+1" not in produced
    assert {"c:plus1", "e:remove_counter", "e:create_token"} <= _flat("Noosegraf Mob", 1)


# ── exile: Exile + [_Exilable ...] ───────────────────────────────────────────

def test_exile_permanent():
    # Swords to Plowshares: "Exile target creature. Its controller gains life equal to its power."
    (rec,) = _recs("Swords to Plowshares")
    assert _verbs(rec)[0] == "Exile.Permanent"
    assert "e:exile" in _flat("Swords to Plowshares")


def test_exile_graveyard_card_then_counter():
    # Scavenging Ooze: "{G}: Exile target card from a graveyard. If it was a creature
    # card, put a +1/+1 counter on this creature and you gain 1 life."
    (rec,) = _recs("Scavenging Ooze")
    assert _verbs(rec) == ["Exile.CardInGraveyards", "PutCounters.ACounterOfTypeOnPermanent", "GainLife"]
    assert {"e:exile", "e:add_counter", "c:plus1", "e:gain_life"} <= _flat("Scavenging Ooze")


def test_exile_with_several_exilables_yields_one_effect_each():
    # Detention Sphere: "When this enchantment enters, you may exile target nonland
    # permanent not named Detention Sphere and all other permanents with the same name
    # as that permanent."
    rec = _recs("Detention Sphere")[0]
    assert _verbs(rec) == ["Exile.Permanent", "Exile.EachPermanent"]
    assert all(e.optional for e in rec.effects)
    assert rec.effects[1].quantifier is None and rec.effects[1].scope == "And"


# ── triggers: _Trigger If wrapper, AnchorWord rule wrapper ───────────────────

def test_if_wrapped_trigger_projects_the_inner_trigger_and_condition():
    # Alacrian Jaguar: "Whenever this creature attacks while saddled, it gets +2/+2 until end of turn."
    rec = _recs("Alacrian Jaguar")[1]
    assert rec.kind == "triggered"
    assert rec.trigger["op"] == "WhenACreatureAttacks"
    assert rec.condition is not None
    assert {"t:attacks", "cond:gated", "e:pump"} <= _flat("Alacrian Jaguar", 1)


def test_anchor_word_rule_projects_the_inner_rule_gated_on_the_word():
    # Barrensteppe Siege: "As this enchantment enters, choose Abzan or Mardu. / • Abzan —
    # At the beginning of your end step, put a +1/+1 counter on each creature you control."
    rec = _recs("Barrensteppe Siege")[1]
    assert rec.kind == "triggered"
    assert rec.trigger["op"] == "AtTheBeginningOfAPlayersEndStep"
    assert rec.condition == {"op": "AnchorWord", "raw": "Abzan"}
    assert rec.raw["_Rule"] == "AnchorWord"          # the source rule stays canonical
    assert {"t:end_step", "cond:gated", "e:add_counter", "c:plus1"} <= _flat("Barrensteppe Siege", 1)


# ── reflexive actions: Reflexive_<step>_When... ──────────────────────────────

def test_reflexive_sacrifice_projects_the_step_and_the_reflexive_body():
    # Minsc & Boo: "−2: Sacrifice a creature. When you do, Minsc & Boo deals X damage
    # to any target, where X is that creature's power. If the sacrificed creature was
    # a Hamster, draw X cards."
    rec = _recs("Minsc & Boo, Timeless Heroes")[2]
    verbs = _verbs(rec)
    assert verbs[0] == "Reflexive_Sacrifice_WhenYouDo"
    assert rec.effects[0].object == "Creature"
    assert {"PermanentDealsDamage", "DrawNumberCards"} <= set(verbs)
    assert rec.condition is not None                 # "When you do" gates the body
    assert {"cond:gated", "perm:creature", "e:sacrifice", "e:damage", "e:draw"} <= _flat(
        "Minsc & Boo, Timeless Heroes", 2)


def test_optional_reflexive_pay_mana():
    # Hurska Sweet-Tooth: "Whenever you gain life, you may pay {G/W}. When you do,
    # target creature gets +X/+X until end of turn, where X is the amount of life you gained."
    rec = _recs("Hurska Sweet-Tooth")[1]
    assert _verbs(rec) == ["Reflexive_PayMana_WhenYouDo", "CreatePermanentLayerEffectUntil"]
    assert rec.optional is True
    assert {"cond:gated", "may:optional", "e:pump", "perm:creature", "t:life_gained"} <= _flat(
        "Hurska Sweet-Tooth", 1)


def test_reflexive_exile_tags_the_exile_step_and_the_body():
    # Kishla Trawlers: "When this creature enters, you may exile a creature card from your
    # graveyard. When you do, return target instant or sorcery card from your graveyard
    # to your hand."
    (rec,) = _recs("Kishla Trawlers")
    assert _verbs(rec) == ["Reflexive_Exile_WhenYouDo", "PutGraveyardCardIntoHand"]
    assert rec.effects[1].targeted and rec.optional
    assert {"e:exile", "e:reanimate", "cond:gated", "may:optional", "t:etb"} <= _flat("Kishla Trawlers")


def test_reflexive_create_tokens_then_fight():
    # Curse of the Werefox: "Create a Monster Role token attached to target creature you
    # control. When you do, that creature fights up to one target creature you don't control. (...)"
    assert {"e:create_token", "e:fight"} <= _flat("Curse of the Werefox")
    assert "token" in card_resources(_recs("Curse of the Werefox"))["produces"]


# ── renamed / new operators ──────────────────────────────────────────────────

def test_fight():
    # Prey Upon: "Target creature you control fights target creature you don't control. (...)"
    assert "e:fight" in _flat("Prey Upon")


def test_prevent_damage_rule_is_a_damage_replacement():
    # Angel of Suffering: "If damage would be dealt to you, prevent that damage and mill
    # twice that many cards."
    rec = _recs("Angel of Suffering")[1]
    assert rec.kind == "replacement"
    assert "r:replace_damage" in _flat("Angel of Suffering", 1)


def test_each_player_creates_tokens():
    # Elephant Resurgence: "Each player creates a green Elephant creature token. Those
    # creatures have ..."
    assert "e:create_token" in _flat("Elephant Resurgence")
    assert "token" in card_resources(_recs("Elephant Resurgence"))["produces"]
    # Captive Audience: "At the beginning of your upkeep, choose one that hasn't been
    # chosen — ... • Each opponent creates five 2/2 black Zombie creature tokens."
    assert "e:create_token" in _flat("Captive Audience", 1)


def test_each_player_action_folds_its_player_scope_into_the_child():
    # Temporary Truce: "Each player may draw up to two cards. For each card less than
    # two a player draws this way, that player gains 2 life." (April: one
    # EachPlayerActions leaf scoped to AnyPlayer; upstream: two EachPlayerAction wrappers.)
    (rec,) = _recs("Temporary Truce")
    assert [e.scope for e in rec.effects] == ["AnyPlayer", "AnyPlayer"]
    assert {"tgt:any_player", "e:gain_life"} <= _flat("Temporary Truce")


def test_teamwork_spell_is_a_spell():
    # Atlantis Attacks: "Teamwork 4 (...) / Choose one. If this spell was cast using
    # teamwork, choose both instead. / • Target player creates a 6/5 blue Leviathan creature
    # token with hexproof. / • Return one or two target nonland permanents to their owners' hands."
    (rec,) = _recs("Atlantis Attacks")
    assert rec.kind == "spell"
    assert {"e:create_token", "tgts:targeted"} <= _flat("Atlantis Attacks")


def test_dies_trigger_still_consumes_death_events():
    # Blood Artist: "Whenever this creature or another creature dies, target player
    # loses 1 life and you gain 1 life."
    assert "death_event" in card_resources(_recs("Blood Artist"))["consumes"]


# ── ability gates the upstream restructure moved ─────────────────────────────

def test_or_trigger_tags_every_part():
    # Voice of Resurgence: "Whenever an opponent casts a spell during your turn and when this
    # creature dies, create a green and white Elemental creature token ..." (April: two rules;
    # upstream: one rule with an Or trigger whose first part is If-wrapped).
    (rec,) = _recs("Voice of Resurgence")
    assert rec.trigger["op"] == "Or"
    assert {"t:cast_spell", "t:creature_dies", "cond:gated", "e:create_token"} <= _flat("Voice of Resurgence")


def test_condition_under_an_added_target_wrapper_is_still_found():
    # Hidetsugu and Kairi: "When Hidetsugu and Kairi dies, exile the top card of your library.
    # Target opponent loses life equal to its mana value. If it's an instant or sorcery card,
    # you may cast it without paying its mana cost." Upstream added the missing target, which
    # wraps the action list in Targeted; the If condition must still gate the ability.
    rec = _recs("Hidetsugu and Kairi")[2]
    assert rec.condition["op"] == "ACardWasExiledThisWay"
    # Dwarven Vigilantes: "... you may have it deal damage equal to its power to target
    # creature. If you do, this creature assigns no combat damage this turn."
    assert _recs("Dwarven Vigilantes")[0].condition["op"] == "CostWasPaid"


def test_if_trigger_inside_a_granted_ability_keeps_its_condition():
    # Dionus, Elvish Archdruid: Elves you control have "Whenever this creature becomes
    # tapped during your turn, untap it and put a +1/+1 counter on it. ..."
    assert _recs("Dionus, Elvish Archdruid")[0].condition["op"] == "IsPlayersTurn"


def test_reflexive_prevention_gates_the_replacement():
    # Phyrexian Vindicator: "If damage would be dealt to this creature, prevent that damage.
    # When damage is prevented this way, this creature deals that much damage to any other target."
    rec = _recs("Phyrexian Vindicator")[1]
    assert rec.kind == "replacement"
    assert rec.condition["op"].startswith("Reflexive_PreventThatDamage")
    assert {"r:replace_damage", "cond:gated"} <= _flat("Phyrexian Vindicator", 1)


def test_reflexive_body_takes_its_target_type():
    # Shrapnel Slinger: "When this creature enters, you may sacrifice a creature. When you do,
    # destroy target artifact an opponent controls."
    rec = _recs("Shrapnel Slinger")[0]
    assert [(e.verb, e.object) for e in rec.effects] == [
        ("Reflexive_Sacrifice_WhenYouDo", "Creature"), ("DestroyPermanent", "Artifact")]
    assert {"perm:creature", "perm:artifact", "e:sacrifice", "e:destroy"} <= _flat("Shrapnel Slinger")
    assert "death_event" in card_resources(_recs("Shrapnel Slinger"))["produces"]


def test_regenerate_when_it_regenerates():
    # Skeleton Scavengers: "Pay {1} for each +1/+1 counter on this creature: Regenerate this
    # creature. When it regenerates this way, put a +1/+1 counter on it."
    rec = _recs("Skeleton Scavengers")[1]
    assert _verbs(rec) == ["RegeneratePermanent_WhenItRengeratesThisWay",
                           "PutCounters.ACounterOfTypeOnPermanent"]
    assert {"e:regenerate", "e:add_counter", "c:plus1", "cond:gated"} <= _flat("Skeleton Scavengers", 1)


# ── choices and per-player containers ────────────────────────────────────────

def test_choose_an_action_with_do_nothing_is_optional():
    # Mairsil, the Pretender: "When Mairsil enters, you may exile an artifact or creature card
    # from your hand or graveyard and put a cage counter on it." (upstream: ChooseAnAction
    # [hand option], [graveyard option], [DoNothing])
    rec = _recs("Mairsil, the Pretender")[0]
    assert "DoNothing" not in _verbs(rec)
    assert {"Exile.ACardOfTypeFromHand", "Exile.ACardInGraveyards"} <= set(_verbs(rec))
    assert rec.optional and all(e.optional for e in rec.effects)
    assert {"may:optional", "e:exile", "e:add_counter"} <= _flat("Mairsil, the Pretender", 0)
    # Jhoira's Timebug: "... you may remove a time counter from it or put another time counter on it."
    assert {"may:optional", "e:add_counter", "e:remove_counter", "c:time"} <= _flat("Jhoira's Timebug")


def test_each_player_may_cost_or_fallback_projects_the_fallback():
    # Bellowing Mauler: "At the beginning of your end step, each player loses 4 life unless
    # they sacrifice a nontoken creature of their choice."
    rec = _recs("Bellowing Mauler")[0]
    assert _verbs(rec) == ["EachPlayerMayCostOrFallback", "LoseLife"]
    assert {"e:lose_life", "amt:high", "tgt:any_player"} <= _flat("Bellowing Mauler")


def test_each_player_may_action_is_an_optional_wrapper():
    # Agitator Ant: "At the beginning of your end step, each player may put two +1/+1 counters
    # on a creature they control. ..."
    (e, _goad) = _recs("Agitator Ant")[0].effects
    assert e.verb == "PutCounters.NumberCountersOfTypeOnAPermanent" and e.optional
    assert e.amount.value == 2 and e.scope == "AnyPlayer"
    assert {"amt:mid", "c:plus1", "may:optional", "tgt:any_player"} <= _flat("Agitator Ant")


def test_each_player_action_scope_replaces_a_permanent_filter_scope():
    # Rite of Ruin: "... Each player sacrifices one permanent of their choice of the first
    # type, sacrifices two ..., then sacrifices three ..." (April: one EachPlayerActions leaf
    # scoped to AnyPlayer; upstream: three EachPlayerAction wrappers)
    effs = _recs("Rite of Ruin")[0].effects
    assert [e.scope for e in effs if e.verb.startswith("Sacrifice")] == ["AnyPlayer"] * 3
    assert {"e:sacrifice", "tgt:any_player"} <= _flat("Rite of Ruin")


def test_action_for_each_target_projects_its_actions():
    # Soulfire Eruption: "... For each of them, exile the top card of your library, then
    # Soulfire Eruption deals damage equal to that card's mana value to that permanent or
    # player. You may play the exiled cards until the end of your next turn."
    verbs = _verbs(_recs("Soulfire Eruption")[0])
    assert {"Exile.TheTopCardOfLibrary", "SpellDealsDamage", "CreatePlayerEffectUntil"} <= set(verbs)
    assert {"e:exile", "e:damage", "tgt:self"} <= _flat("Soulfire Eruption")


# ── graveyard owners, exile flags, token selectors ───────────────────────────

def test_graveyard_exile_reads_the_owner_from_the_card_filter():
    # Rest in Peace: "When this enchantment enters, exile all graveyards. ..."
    e = _recs("Rest in Peace")[0].effects[0]
    assert (e.verb, e.scope) == ("Exile.EachCardInGraveyards", "AnyPlayer")
    assert "tgt:any_player" in _flat("Rest in Peace")
    # Yggdrasil, Rebirth Engine: "When Yggdrasil enters, exile all creature cards from your graveyard."
    e = _recs("Yggdrasil, Rebirth Engine")[0].effects[0]
    assert (e.verb, e.scope) == ("Exile.EachCardInGraveyards", "You")
    assert "tgt:self" in _flat("Yggdrasil, Rebirth Engine", 0)


def test_exile_flag_counters_and_amount():
    # Rousing Refrain: "... Exile Rousing Refrain with three time counters on it."
    e = _recs("Rousing Refrain")[0].effects[1]
    assert e.verb == "Exile.Spell" and e.counter == "time" and e.amount.value == 3
    assert {"e:exile", "c:time", "amt:mid"} <= _flat("Rousing Refrain", 0)


def test_token_object_comes_from_the_token_list_or_the_selector():
    # Nomads' Assembly: "Create a 1/1 white Kor Soldier creature token for each creature you control."
    assert _recs("Nomads' Assembly")[0].effects[0].object == "Creature"
    # Asinine Antics: "For each creature your opponents control, create a Cursed Role token
    # attached to that creature."
    e = _recs("Asinine Antics")[1].effects[0]
    assert (e.verb, e.object) == ("CreateTokensForEachPermanent", "Creature")
    assert {"e:create_token", "perm:creature"} <= _flat("Asinine Antics")


def test_counter_nested_in_a_delayed_trigger_is_found():
    # Phelia, Exuberant Shepherd: "... At the beginning of the next end step, return that card
    # to the battlefield under its owner's control. If it entered under your control, put a
    # +1/+1 counter on Phelia."
    assert "c:plus1" in _flat("Phelia, Exuberant Shepherd", 1)


# ── renamed operators ────────────────────────────────────────────────────────

def test_ops_on_the_created_tokens_as_a_group():
    # Feldon of the Third Path: "... Create a token that's a copy of target creature card in
    # your graveyard ... It gains haste. Sacrifice it at the beginning of the next end step."
    # Upstream: TheTokensCreatedThisWay + CreateEachPermanentLayerEffect / SacrificeEachPermanent.
    assert {"e:create_token", "e:pump", "e:sacrifice"} <= _flat("Feldon of the Third Path")
    # Rolling Hamsphere: "... create three 1/1 red Hamster creature tokens, then it deals X damage
    # to any target ..." (upstream: EachPermanentDealsDamage)
    assert "e:damage" in _flat("Rolling Hamsphere", 1)
    # Cauldron Dance: "Return it to your hand at the beginning of the next end step. ...
    # Its controller sacrifices it at the beginning of the next end step."
    # Both delayed actions are the bodies of CreateFutureTrigger.
    bodies = [s.verb for e in _recs("Cauldron Dance")[1].effects
              if e.verb == "CreateFutureTrigger" for s in e.sub_effects]
    assert {"PutPermanentIntoItsOwnersHand", "ControllersSacrificeEachPermanent"} <= set(bodies)
    assert {"e:sacrifice", "e:bounce"} <= _flat("Cauldron Dance", 1)
    # Cut the Tethers: "For each Spirit, return it to its owner's hand unless that player pays {3}."
    assert "e:bounce" in _flat("Cut the Tethers")


def test_counter_placed_trigger_upstream_name():
    # Hollowmurk Siege: "• Sultai — Whenever a counter is put on a creature you control, draw a
    # card. This ability triggers only once each turn."
    rec = _recs("Hollowmurk Siege")[1]
    assert rec.trigger["op"] == "WhenAnyNumberOfCountersArePutOnAPermanent"
    assert {"t:counter_placed", "e:draw", "cond:gated"} <= _flat("Hollowmurk Siege", 1)
    assert "counter" in card_resources([rec])["consumes"]


def test_multi_draw_and_multi_create_tokens():
    # Master of Ceremonies: "... you and that player each create a Treasure token ... each
    # create a 1/1 green and white Citizen creature token ... each draw a card."
    assert {"e:create_token", "e:draw"} <= _flat("Master of Ceremonies")
    assert {"token", "card"} <= card_resources(_recs("Master of Ceremonies"))["produces"]


def test_look_at_top_new():
    # Gilgamesh, Master-at-Arms: "Whenever Gilgamesh enters or attacks, look at the top six cards
    # of your library. You may put any number of Equipment cards from among them onto the
    # battlefield. ... When you put one or more Equipment onto the battlefield this way, you may
    # attach one of them to a Samurai you control."
    assert {"e:scry", "e:equip", "t:etb", "t:attacks", "cond:gated"} <= _flat("Gilgamesh, Master-at-Arms")


def test_duplicate_counter_variants_keep_the_legacy_proliferate_tag():
    # Contractual Safeguard: "... Choose a kind of counter on a creature you control. Put a
    # counter of that kind on each other creature you control."
    assert {"e:add_counter", "e:proliferate"} <= _flat("Contractual Safeguard")
