"""Derive flat tags / inverted index / feature vectors from AbilityRecords.

Pure projection of the canonical records. Reuses the existing tag_taxonomy maps
for verb/trigger naming and adds quantifier/amount/cost/targeting/optional/
condition namespaces so 'burn-each' and 'burn-one-targeted' are distinguishable.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tag_taxonomy import (  # noqa: E402
    ACTION_MAP, TRIGGER_MAP, PERMANENT_CARDTYPE_MAP,
)

from .schema import AbilityRecord, Effect, Amount  # noqa: E402


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
    tags: set[str] = set(ACTION_MAP.get(e.verb, []))
    if e.quantifier:
        tags.add(f"q:{e.quantifier}")
    if e.targeted:
        tags.add("tgts:targeted")
    if e.optional:
        tags.add("may:optional")
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
        if rec.trigger:
            tags.update(TRIGGER_MAP.get(rec.trigger.get("op", ""), []))
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
