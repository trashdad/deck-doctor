"""Derive flat tags / inverted index / feature vectors from AbilityRecords.

Pure projection of the canonical records. Reuses the existing tag_taxonomy maps
for verb/trigger naming and adds quantifier/amount/cost/targeting/optional/
condition namespaces so 'burn-each' and 'burn-one-targeted' are distinguishable.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tag_taxonomy import (  # noqa: E402
    TRIGGER_MAP, PERMANENT_CARDTYPE_MAP, KEYWORD_MAP, REPLACEMENT_MAP,
    PLAYER_MAP, PLAYERS_MAP, action_tags,
)
from mtgish_schema import core_rule, trigger_ops  # noqa: E402

from .schema import AbilityRecord, Effect, Amount  # noqa: E402


def _rule_static_tags(rec: AbilityRecord) -> set[str]:
    """Tags from a record's top-level `_Rule` op (keyword/replacement abilities).

    Keyword-only and replacement abilities are static records with no effects;
    their behavior lives in the canonical `raw` _Rule op. Mirrors the proven
    mapping from the prior build_semantics pipeline so keyword coverage holds.
    """
    op = core_rule(rec.raw or {}).get("_Rule", "")   # through an upstream AnchorWord gate
    tags: set[str] = set(KEYWORD_MAP.get(op, []))
    tags.update(REPLACEMENT_MAP.get(op, []))
    if op == "Landfall":
        tags.update({"t:landfall", "k:landfall"})
    return tags


def _amount_bucket(amt: Amount | None) -> str | None:
    if amt is None:
        return None
    if amt.kind == "dynamic":
        return "amt:dynamic"
    if amt.kind == "x":
        return "amt:x"
    v = amt.value or 0
    if v <= 1:
        return "amt:low"
    if v <= 3:
        return "amt:mid"
    return "amt:high"


def _effect_tags(e: Effect) -> set[str]:
    tags: set[str] = set(action_tags(e.verb))      # variant-qualified verbs fall back to the op
    if e.quantifier:
        tags.add(f"q:{e.quantifier}")
    if e.targeted:
        tags.add("tgts:targeted")
    if e.optional:
        tags.add("may:optional")
    if e.counter:
        tags.add(f"c:{e.counter}")
    if e.scope:                       # player target: You -> tgt:self, Opponent -> tgt:opponent
        tags.update(PLAYER_MAP.get(e.scope, []))
        tags.update(PLAYERS_MAP.get(e.scope, []))
    if e.object:
        tags.update(PERMANENT_CARDTYPE_MAP.get(e.object, []))
    bucket = _amount_bucket(e.amount)
    if bucket:
        tags.add(bucket)
    for sub in e.sub_effects:
        tags |= _effect_tags(sub)
    return tags


def flat_tags(records: list[AbilityRecord]) -> list[str]:
    """Per-card union of derived tags (sorted, deterministic)."""
    tags: set[str] = set()
    for rec in records:
        tags |= _rule_static_tags(rec)
        for op in trigger_ops(rec.trigger):     # every part of an "Or"/"If" trigger
            tags.update(TRIGGER_MAP.get(op, []))
        if rec.cost:
            if rec.cost.get("tap"):
                tags.add("cost:tap")
            if rec.cost.get("sacrifice"):
                tags.add("cost:sacrifice")
        if rec.condition:
            tags.add("cond:gated")
        if rec.optional:
            tags.add("may:optional")
        for e in rec.effects:
            tags |= _effect_tags(e)
    return sorted(tags)


def ability_tag_lists(records: list[AbilityRecord]) -> list[list[str]]:
    """One sorted tag list per ability (keeps ability_idx alignment)."""
    return [sorted(_per_ability_tags(rec)) for rec in records]


def _per_ability_tags(rec: AbilityRecord) -> set[str]:
    return set(flat_tags([rec]))


def build_inverted_index(per_card_tags: dict[str, list[str]]) -> dict[str, list[str]]:
    """tag -> sorted list of card ids."""
    inv: dict[str, set[str]] = defaultdict(set)
    for card_id, tags in per_card_tags.items():
        for t in tags:
            inv[t].add(card_id)
    return {t: sorted(inv[t]) for t in sorted(inv)}


def fingerprint_to_vector(records: list[AbilityRecord]) -> dict[str, int]:
    """Structured feature vector (sparse dict).

    SP1 owns the final shape/weighting; this is the documented seam and is
    designed for late fusion with an SP3 co-occurrence embedding. Counts are
    interpretable and stand alone for cold-start (unseen) cards.
    """
    vec: dict[str, int] = defaultdict(int)
    vec["targeted"] = 0
    for rec in records:
        vec[f"kind:{rec.kind}"] += 1
        for t in _rule_static_tags(rec):
            vec[t] += 1
        if rec.cost and rec.cost.get("tap"):
            vec["cost:tap"] += 1
        if rec.condition:
            vec["cond:gated"] += 1
        for e in _iter_effects(rec.effects):
            vec[f"verb:{e.verb}"] += 1
            if e.quantifier:
                vec[f"q:{e.quantifier}"] += 1
            if e.targeted:
                vec["targeted"] += 1
            if e.amount:
                vec[f"amt:{e.amount.kind}"] += 1
    return {k: vec[k] for k in sorted(vec)}


def _iter_effects(effects: list[Effect]):
    for e in effects:
        yield e
        yield from _iter_effects(e.sub_effects)
