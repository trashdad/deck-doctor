"""Map SP2 fingerprint records to produced / consumed typed resources.

The resource-flow graph (graph.py) and all synergy/engine logic read these sets.
The maps are a deterministic seed taxonomy keyed on the raw MTGish verb / trigger
op / cost / counter the fingerprint already captured; they are intended to grow.
"""

from __future__ import annotations

from fingerprints.schema import AbilityRecord

# verb (_Action op) -> resource the effect PRODUCES
PRODUCER_VERB = {
    "AddMana": "mana", "AddManaWithModifiers": "mana", "AddManaRepeated": "mana",
    "CreateTokens": "token", "CreateNumberTokens": "token",
    "CreateTokensWithFlags": "token", "ForEachPlayerCreateTokens": "token",
    "Populate": "token", "PopulateNumberTimes": "token",
    "DrawACard": "card", "DrawNumberCards": "card", "DrawACardForEach": "card",
    "DrawUntilHandSize": "card",
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
    "SacrificeNumberPermanents",
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


def _effect_products(effects, out: set) -> None:
    for e in effects:
        if e.verb in PRODUCER_VERB:
            out.add(PRODUCER_VERB[e.verb])
            # Tokens are also sacrifice fodder — links go-wide makers into the
            # aristocrats engine (token maker -> sac outlet -> death payoff).
            if PRODUCER_VERB[e.verb] == "token":
                out.add("sacrifice_fodder")
        if e.verb in DEATH_VERBS:
            out.add("death_event")
        if e.counter:
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
