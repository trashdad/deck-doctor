"""Map SP2 fingerprint records to produced / consumed typed resources.

The resource-flow graph (graph.py) and all synergy/engine logic read these sets.
The maps are a deterministic seed taxonomy keyed on the raw MTGish verb / trigger
op / cost / counter the fingerprint already captured; they are intended to grow.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fingerprints.schema import AbilityRecord  # noqa: E402
from mtgish_schema import reflexive_steps  # noqa: E402
from tag_taxonomy import REFLEXIVE_STEP_ACTION  # noqa: E402

# verb (_Action op) -> resource the effect PRODUCES
PRODUCER_VERB = {
    "AddMana": "mana", "AddManaWithModifiers": "mana", "AddManaRepeated": "mana",
    "CreateTokens": "token", "CreateNumberTokens": "token",
    "CreateTokensWithFlags": "token", "ForEachPlayerCreateTokens": "token",
    # upstream MTGish (2026-10) names of the token makers
    "EachPlayerCreatesTokens": "token", "EachPlayerMayCreateTokens": "token",
    "EachPlayerCreatesTokensOfTheirChoice": "token", "CreateTokensForEachPlayer": "token",
    "CreateTokensForEachPermanent": "token", "MultiCreateTokens": "token",
    "Populate": "token", "PopulateNumberTimes": "token",
    "DrawACard": "card", "DrawNumberCards": "card", "DrawACardForEach": "card",
    "DrawUntilHandSize": "card", "MultiDraw": "card",
    "GainLife": "life", "GainLifeForEach": "life", "GainLifeEqualToDamage": "life",
    "UntapPermanent": "untap", "UntapAllPermanents": "untap", "UntapEachPermanent": "untap",
    "SearchLibrary": "tutor", "SearchLibraryAndGraveyard": "tutor", "SeekACard": "tutor",
    "ReturnACardFromGraveyard": "reanimate", "ReturnPermanentFromGraveyard": "reanimate",
    "CastGraveyardCardWithoutPaying": "reanimate", "PutGraveyardCardOntoBattlefield": "reanimate",
}

# verbs that cause permanents to leave the battlefield -> produce "death_event"
DEATH_VERBS = {
    "DestroyAllPermanents", "DestroyEachPermanent", "DestroyAllCreatures",
    "ExileAllCreatures", "SacrificePermanent", "SacrificeAPermanent",
    "SacrificeNumberPermanents", "SacrificeEachPermanent", "ControllersSacrificeEachPermanent",
}

# trigger op -> resource the ability CONSUMES (pays off / cares about)
TRIGGER_CONSUMER = {
    "WhenAPermanentDies": "death_event",
    "WhenACreatureOrPlaneswalkerDies": "death_event",
    "WhenAPermanentIsSacrificed": "death_event",
    "WhenAPlayerSacrificesAPermanent": "death_event",
    "WhenATokenEntersTheBattlefield": "token",
    "WhenATokenIsCreated": "token",
    "WhenAPlayerGainsLife": "life",
    "WhenACounterOfTypeIsPutOnAPermanent": "counter",
    "WhenACounterIsPutOnAPermanent": "counter",
    "WhenAnyNumberOfCountersArePutOnAPermanent": "counter",
    "WhenAPlayerCastsASpell": "spell_cast",
    "WhenAPlayerCastsANonCreatureSpell": "spell_cast",
    "WhenACreatureAttacks": "attack_trigger",
    "WhenALandEntersTheBattlefield": "landfall",
}


def resource_match(produced: str, consumed: str) -> bool:
    """A produced resource satisfies a consumed one (with generic 'counter')."""
    if produced == consumed:
        return True
    if consumed == "counter" and produced.startswith("counter:"):
        return True
    if produced == "counter" and consumed.startswith("counter:"):
        return True
    return False


def _verb_keys(verb: str) -> list[str]:
    """Lookup keys for a verb: itself, its plain op when variant-qualified
    ("Exile.Permanent" -> "Exile"), and the actions a Reflexive_* verb's steps name."""
    base = verb.split(".", 1)[0]
    keys = [verb] if base == verb else [verb, base]
    keys += [REFLEXIVE_STEP_ACTION.get(s, s) for s in reflexive_steps(base)]
    return keys


# Ops whose counter field names the counter they take away, not one they place.
# April's RemoveACounter* ops and upstream RemoveCounters share that field.
_COUNTER_REMOVAL_OPS = frozenset({
    "RemoveCounters",
    "RemoveACounterOfTypeFromPermanent",
    "RemoveNumberCountersOfTypeFromPermanent",
})
_COUNTER_PLACING_STEPS = frozenset({"PutCounters", "MoveCounters"})


def _places_counter(verb: str) -> bool:
    """True when this effect's counter slug is a counter it puts on an object.

    RemoveCounters (and a reflexive step that only removes) carries the same
    slug for the counter it takes away. MoveCounters still places one.
    """
    base = verb.split(".", 1)[0]
    if base in _COUNTER_REMOVAL_OPS:
        return False
    steps = reflexive_steps(base)
    if steps and any(s in _COUNTER_REMOVAL_OPS for s in steps):
        if not any(s in _COUNTER_PLACING_STEPS for s in steps):
            return False
    return True


def _effect_products(effects, out: set) -> None:
    for e in effects:
        for key in _verb_keys(e.verb):
            if key in PRODUCER_VERB:
                out.add(PRODUCER_VERB[key])
                # Tokens are also sacrifice fodder — links go-wide makers into the
                # aristocrats engine (token maker -> sac outlet -> death payoff).
                if PRODUCER_VERB[key] == "token":
                    out.add("sacrifice_fodder")
            if key in DEATH_VERBS:
                out.add("death_event")
        if e.counter and _places_counter(e.verb):
            out.add(f"counter:{_counter_label(e.counter)}")
            out.add("counter")
        _effect_products(e.sub_effects, out)


def _counter_label(slug: str) -> str:
    return {"plus1": "+1/+1", "minus1": "-1/-1"}.get(slug, slug)


def _trigger_ops(trigger: dict) -> set[str]:
    """All trigger operator strings: the top-level op plus any nested `_Trigger`
    ops inside its raw args. Combiner triggers like "Or" (e.g. "~ or another
    creature dies") wrap the real triggers in raw, so we must look inside."""
    ops: set[str] = set()
    op = trigger.get("op")
    if op:
        ops.add(op)

    def walk(node) -> None:
        if isinstance(node, dict):
            t = node.get("_Trigger")
            if isinstance(t, str):
                ops.add(t)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(trigger.get("raw"))
    return ops


def card_resources(records: list[AbilityRecord]) -> dict:
    """Return {'produces': set[str], 'consumes': set[str]} for a card."""
    produces: set[str] = set()
    consumes: set[str] = set()
    for rec in records:
        _effect_products(rec.effects, produces)
        if rec.trigger:
            for op in _trigger_ops(rec.trigger):
                r = TRIGGER_CONSUMER.get(op)
                if r:
                    consumes.add(r)
        if rec.cost:
            if rec.cost.get("tap"):
                consumes.add("untap")
            if rec.cost.get("sacrifice"):
                consumes.add("sacrifice_fodder")
                produces.add("death_event")   # a sac outlet kills permanents
        # "for each <object>" dynamic amounts mean the card cares about that object
        for e in rec.effects:
            if e.amount and e.amount.kind == "dynamic" and e.amount.count:
                obj = (e.amount.count.get("counted_object") or "").lower()
                if "token" in obj:
                    consumes.add("token")
    return {"produces": produces, "consumes": consumes}
