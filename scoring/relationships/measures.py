"""The four typed pair measures: similarity, synergy (directional), anti_synergy.

similarity  : cosine over fingerprint_to_vector dicts (redundancy axis).
synergy     : directional resource producer->consumer match (enabling axis).
anti_synergy: conservative rule-based anti-pattern detection.
These are different axes by design (two ramp rocks: similar, not synergistic).
"""

from __future__ import annotations

import math

from relationships.resources import resource_match


def similarity(vec_a: dict, vec_b: dict) -> float:
    """Cosine similarity over two sparse feature-count dicts, in [0, 1]."""
    if not vec_a or not vec_b:
        return 0.0
    dot = sum(v * vec_b.get(k, 0) for k, v in vec_a.items())
    na = math.sqrt(sum(v * v for v in vec_a.values()))
    nb = math.sqrt(sum(v * v for v in vec_b.values()))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return round(dot / (na * nb), 4)


SYNERGY_K = 0.8   # squash steepness; calibrated against the golden set


def _squash(raw: float, k: float = SYNERGY_K) -> float:
    """Monotonic map of a non-negative raw score into [0, 1)."""
    return round(1.0 - math.exp(-k * raw), 4)


def _directional_raw(prod: set, cons: set) -> float:
    """Count consumed resources that are satisfied by at least one produced one.

    Counting per consumed resource (not per produced×consumed match) avoids
    double-counting: a counter producer adds both "counter:+1/+1" and the generic
    "counter", which would otherwise score a single generic-counter consumer twice.
    """
    return float(sum(1 for c in cons if any(resource_match(p, c) for p in prod)))


def synergy(res_a: dict, res_b: dict) -> tuple[float, float]:
    """Directional synergy (ab, ba): A produces what B consumes, and vice versa."""
    ab = _squash(_directional_raw(res_a["produces"], res_b["consumes"]))
    ba = _squash(_directional_raw(res_b["produces"], res_a["consumes"]))
    return ab, ba


# Conservative anti-pattern rules over SP2 flat tags: (tagset_x, tagset_y, weight).
# Fires when card_x has all of tagset_x AND card_y has all of tagset_y (either order).
# Intentionally small in v1; the strong anti-synergy signal is SP3 negative co-occurrence.
ANTI_RULES: list[tuple[set, set, float]] = [
    ({"e:draw"}, {"cond:hellbent"}, 1.0),     # refills hand vs rewards-empty-hand
]


def anti_synergy(tags_a: set, tags_b: set) -> float:
    """Conservative rule-based anti-synergy in [0, 1]. Order-independent."""
    ta, tb = set(tags_a), set(tags_b)
    raw = 0.0
    for left, right, w in ANTI_RULES:
        if left <= ta and right <= tb:
            raw += w
        if left <= tb and right <= ta:
            raw += w
    return _squash(raw)
