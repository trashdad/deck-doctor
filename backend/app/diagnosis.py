"""Deck Doctor Diagnosis — the headline 0–100 vitals scorecard.

Turns a working deck into the five "vitals" + an overall Diagnosis score and a
one-word verdict, matching the design-previews/option-7 gauge. This is a thin,
deterministic grading layer that REUSES existing detection:

  * ``doctor.category_of`` for ramp / card_draw / removal counts (the same
    server-side zoning the deck completion uses),
  * ``store.get(...)["wincon"]`` (``store.is_wincon``) for win-condition quality,
  * the mana curve already produced by ``analysis.analyze``.

No model inference, no randomness — pure lookups, so it stays request-cheap.
"""

from __future__ import annotations

from collections import Counter

from .doctor import category_of
from .store import Store

# Sensible Commander targets for a 99-card (+commander) deck. A vital scores 100
# at/above target and degrades linearly toward 0 as the count falls to zero.
RAMP_TARGET = 10
DRAW_TARGET = 10
REMOVAL_TARGET = 9          # removal + board wipes combined
WINCON_TARGET = 3           # ~3 dedicated finishers is a healthy top end

# Overall score = weighted blend of the five vitals. Win Conditions and Mana
# Curve are the load-bearing "is this deck coherent + can it close?" axes, so
# they carry slightly more weight; ramp/draw/removal round out consistency.
VITAL_WEIGHTS = {
    "Mana Curve": 0.25,
    "Ramp": 0.15,
    "Card Draw": 0.15,
    "Removal": 0.20,
    "Win Conditions": 0.25,
}

# Verdict bands keyed off the overall score (see module docstring / spec).
_VERDICTS = [
    (90, "OPTIMAL"),
    (75, "STABLE"),
    (60, "FAIR"),
    (40, "UNSTABLE"),
    (0, "CRITICAL"),
]


def _verdict(score: int) -> str:
    for floor, word in _VERDICTS:
        if score >= floor:
            return word
    return "CRITICAL"


def _ratio_score(count: int, target: int) -> int:
    """0–100, linear up to `target`, capped at 100 (surplus isn't penalised)."""
    if target <= 0:
        return 0
    return int(round(min(1.0, count / target) * 100))


def _curve_score(curve: Counter[int], nonland: int) -> int:
    """Grade the nonland mana curve against an idealised EDH shape.

    Ideal weighting peaks at 2–3 CMC and tapers at the top end. We compare the
    deck's CMC distribution to that ideal with a simple overlap (1 - half the
    total absolute difference between the two normalised distributions), which
    yields 100 for a perfect match and degrades smoothly with distortion
    (too top-heavy or too many one-drops).
    """
    if nonland <= 0:
        return 0
    # Ideal share of nonland spells per CMC bucket (0,1,2,3,4,5,6+).
    ideal = {0: 0.05, 1: 0.13, 2: 0.22, 3: 0.22, 4: 0.16, 5: 0.11, 6: 0.11}
    actual: dict[int, float] = {}
    for cmc, n in curve.items():
        bucket = min(int(cmc), 6)
        actual[bucket] = actual.get(bucket, 0.0) + n / nonland
    diff = sum(abs(ideal.get(b, 0.0) - actual.get(b, 0.0))
               for b in set(ideal) | set(actual))
    overlap = 1.0 - diff / 2.0   # diff is in [0,2]; overlap in [0,1]
    return int(round(max(0.0, overlap) * 100))


def diagnose(store: Store, entries: list[dict], commander_id: str | None) -> dict:
    """Compute the Diagnosis scorecard for a working deck.

    Empty deck → score 0, verdict "—", all vitals 0 (graceful, never raises).
    Returns a dict shaped like the ``DeckDiagnosis`` model.
    """
    cards: list[dict] = []
    for e in entries:
        card = store.get(e["id"])
        if card:
            for _ in range(max(1, e.get("quantity", 1))):
                cards.append(card)

    labels = ["Mana Curve", "Ramp", "Card Draw", "Removal", "Win Conditions"]
    if not cards:
        return {"score": 0, "verdict": "—",
                "vitals": [{"label": lbl, "score": 0} for lbl in labels]}

    curve: Counter[int] = Counter()
    cats: Counter[str] = Counter()
    nonland = 0
    wincons = 0
    for c in cards:
        cat = category_of(c)
        cats[cat] += 1
        if cat != "land":
            curve[int(c.get("cmc") or 0)] += 1
            nonland += 1
        if c.get("wincon"):
            wincons += 1

    removal_count = cats["removal"] + cats["board_wipe"]
    vital_scores = {
        "Mana Curve": _curve_score(curve, nonland),
        "Ramp": _ratio_score(cats["ramp"], RAMP_TARGET),
        "Card Draw": _ratio_score(cats["card_draw"], DRAW_TARGET),
        "Removal": _ratio_score(removal_count, REMOVAL_TARGET),
        "Win Conditions": _ratio_score(wincons, WINCON_TARGET),
    }

    overall = int(round(sum(vital_scores[k] * w for k, w in VITAL_WEIGHTS.items())))
    overall = max(0, min(100, overall))

    return {
        "score": overall,
        "verdict": _verdict(overall),
        "vitals": [{"label": lbl, "score": vital_scores[lbl]} for lbl in labels],
    }
