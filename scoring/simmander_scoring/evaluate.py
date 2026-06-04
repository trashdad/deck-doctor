"""IER / CSS / DER scoring — the core of Doc A's card-evaluation framework.

Terminology (verbatim from the research doc):

* IER (Isolated Efficiency Rating): a card's raw value in a vacuum, 1.0–20.0,
  from mana value, card-advantage potential, and raw stats.
* CSS (Combinatorial Synergy Score): a multiplier for how two mechanics overlap.
  0 = no synergy (purely additive), ~1.0 = linear, 2.0+ = exponential.
* DER (Dynamic Efficiency Ratio): the realized value of a pair, defined as
      DER = IER_A + IER_B + (IER_A * CSS)

Note on the formula vs. the doc's worked example: the doc gives IER_A=5.6,
IER_B=13.1, "additive value 18.7", and a synergistic DER of 45.3. That is only
self-consistent if CSS=0 means *no* synergy (DER == additive). We therefore treat
CSS as starting at 0.0 and climbing with overlap, and document that here so the
single source of truth lives next to the code.

All functions are deterministic and dependency-free. The heavy-scale path
(embeddings + FAISS ANN over 32k cards) is layered on top in pipeline.py; this
module stays exact and unit-testable.
"""

from __future__ import annotations

from .mechanics import (
    COMPLEMENTARY_PAIRS,
    CardTags,
    jaccard,
    tag_card,
)

IER_MIN = 1.0
IER_MAX = 20.0
CSS_MAX = 5.0


def _to_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def isolated_efficiency_rating(card: dict) -> float:
    """Heuristic IER in [1.0, 20.0].

    Rewards low mana value, unconditional card advantage, and efficient bodies;
    tolerant of missing keys. This is intentionally a transparent heuristic — the
    documented seam where simmander's machine-coded value fields take over.
    """
    cmc = card.get("cmc")
    cmc = float(cmc) if isinstance(cmc, (int, float)) else 0.0
    oracle = (card.get("oracle_text") or "").lower()
    type_line = (card.get("type_line") or "").lower()
    tags = tag_card(card)

    score = 6.0  # neutral baseline

    # Mana efficiency: cheaper is better, with diminishing penalty for big bombs.
    score += max(-6.0, 3.0 - cmc * 0.9)

    # Card advantage is the strongest lever.
    if "card_draw" in tags.mechanic_tags:
        score += 4.0
    if "ramp" in tags.mechanic_tags:
        score += 2.5
    if "removal" in tags.mechanic_tags:
        score += 2.0
    if "board_wipe" in tags.mechanic_tags:
        score += 3.0

    # Unconditional effects beat conditional ones.
    if "unless" in oracle or "if you" in oracle or "only if" in oracle:
        score -= 1.0

    # Raw stats: power+toughness relative to cost for creatures.
    if "creature" in type_line:
        stats = _to_int(card.get("power")) + _to_int(card.get("toughness"))
        if cmc > 0:
            score += min(4.0, (stats / cmc) * 0.8)
        else:
            score += min(4.0, stats * 0.8)

    # Lands are cheap enablers, not standalone value.
    if "land" in type_line and "creature" not in type_line:
        score = min(score, 7.0)

    return round(max(IER_MIN, min(IER_MAX, score)), 2)


def combinatorial_synergy_score(
    tags_a: CardTags,
    tags_b: CardTags,
) -> float:
    """CSS multiplier in [0.0, CSS_MAX] from two cards' behavioral tags."""
    css = 0.0

    # Complementary producer -> payoff overlaps drive exponential synergy.
    for producer, payoff in COMPLEMENTARY_PAIRS:
        a_makes = producer in tags_a.mechanic_tags and payoff in tags_b.mechanic_tags
        b_makes = producer in tags_b.mechanic_tags and payoff in tags_a.mechanic_tags
        if a_makes or b_makes:
            css += 2.0

    # Shared parasitic mechanic = high Lift; these cards are bound to each other.
    shared_parasitic = tags_a.parasitic & tags_b.parasitic
    if shared_parasitic:
        css += 2.5 + 0.5 * (len(shared_parasitic) - 1)

    # Mild reward for generally overlapping archetypes (shared non-parasitic tags).
    overlap = jaccard(tags_a.mechanic_tags, tags_b.mechanic_tags)
    css += overlap * 0.75

    return round(min(CSS_MAX, css), 3)


def dynamic_efficiency_ratio(ier_a: float, ier_b: float, css: float) -> float:
    """DER = IER_A + IER_B + (IER_A * CSS)."""
    return round(ier_a + ier_b + (ier_a * css), 2)


def has_lift(tags_a: CardTags, tags_b: CardTags) -> bool:
    """Association-rule Lift flag: pair shares a parasitic mechanic cluster."""
    return bool(tags_a.parasitic & tags_b.parasitic)


def score_pair(card_a: dict, card_b: dict) -> dict:
    """Convenience: full pair evaluation from two raw card dicts."""
    ta, tb = tag_card(card_a), tag_card(card_b)
    ier_a = isolated_efficiency_rating(card_a)
    ier_b = isolated_efficiency_rating(card_b)
    css = combinatorial_synergy_score(ta, tb)
    return {
        "a": card_a.get("id"),
        "b": card_b.get("id"),
        "ier_a": ier_a,
        "ier_b": ier_b,
        "css": css,
        "der": dynamic_efficiency_ratio(ier_a, ier_b, css),
        "lift": has_lift(ta, tb),
    }
