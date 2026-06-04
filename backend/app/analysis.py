"""Deck analysis — the visualization/scoring layer from Doc B.

Combines, in one pass over a decklist:
  * mana curve, color-pip and type distributions (Deckstats/ManaBox style)
  * a hypergeometric "playability" probability (Deckstats style)
  * DeckCheck-style gauges: Efficiency (0-10), Impact (0-10), Average Playability
    (%), and a Score out of 1000
  * a Moxfield-style minimum Bracket (1-5) with the reasons that set it
All inputs come from the precomputed store, so this stays cheap and deterministic.
"""

from __future__ import annotations

import math
from collections import Counter

from .store import Store

# Heuristic flags that push the minimum bracket up (Moxfield-style detection).
_BRACKET_FLAGS = {
    "mass land denial": ["destroy all lands", "each player sacrifices a land"],
    "extra turns": ["take an extra turn"],
    "fast mana": ["sol ring", "mana crypt", "add {c}{c}"],
    "infinite combo marker": ["infinite"],
}


def _hypergeometric_at_least_one(successes: int, deck_size: int, draws: int) -> float:
    """P(>=1 success) drawing `draws` from a `deck_size` deck with `successes` hits."""
    if successes <= 0 or deck_size <= 0 or draws <= 0:
        return 0.0
    draws = min(draws, deck_size)
    # P(0 successes) = C(N-K, n) / C(N, n)
    miss = deck_size - successes
    if miss < draws:
        return 1.0
    p_zero = (
        math.comb(miss, draws) / math.comb(deck_size, draws)
        if math.comb(deck_size, draws)
        else 0.0
    )
    return round((1.0 - p_zero) * 100, 1)


def analyze(store: Store, entries: list[dict], commander_id: str | None) -> dict:
    cards = []
    for e in entries:
        card = store.get(e["id"])
        if card:
            for _ in range(max(1, e.get("quantity", 1))):
                cards.append(card)

    card_count = len(cards)
    ids = [c["id"] for c in cards]

    # --- distributions ---
    curve = Counter()
    pips = Counter()
    types = Counter()
    iers: list[float] = []
    ramp_count = draw_count = 0

    for c in cards:
        cmc = int(c.get("cmc") or 0)
        if "land" not in (c.get("type_line") or "").lower():
            curve[cmc] += 1
        for sym in c.get("color_identity") or []:
            pips[sym] += 1
        primary = (c.get("type_line") or "Other").split("—")[0].strip().split()
        types[primary[-1] if primary else "Other"] += 1
        if c.get("ier") is not None:
            iers.append(c["ier"])
        tags = c.get("mechanic_tags") or []
        if "ramp" in tags:
            ramp_count += 1
        if "card_draw" in tags:
            draw_count += 1

    mana_curve = [{"cmc": k, "count": curve[k]} for k in sorted(curve)]

    # --- synergy edges within the deck ---
    edges = store.synergies_among(ids, limit=20)
    lift_hits = sum(1 for e in edges if e["lift"])

    # --- DeckCheck-style gauges ---
    mean_ier = sum(iers) / len(iers) if iers else 6.0
    efficiency = round(min(10.0, mean_ier / 2.0), 1)  # IER 0-20 -> 0-10
    # Impact = synergy density: how much realized value the engine produces.
    impact_raw = sum(e["der"] for e in edges[:10])
    impact = round(min(10.0, impact_raw / 40.0), 1)
    # Playability: chance to have a ramp/draw enabler in the opening 7.
    enablers = ramp_count + draw_count
    average_playability = _hypergeometric_at_least_one(enablers, max(card_count, 1), 7)
    score = int(min(1000, round(efficiency * 40 + impact * 50 + average_playability * 1.0 + lift_hits * 10)))

    # --- Moxfield-style minimum bracket ---
    bracket, reasons = _estimate_bracket(cards, lift_hits)

    # --- keepable-hand proxy: P(>=3 lands in opening 7) ---
    land_count = sum(1 for c in cards if "land" in (c.get("type_line") or "").lower())
    keepable = _p_at_least_k(land_count, max(card_count, 1), 7, 3)

    return {
        "card_count": card_count,
        "mana_curve": mana_curve,
        "color_pips": dict(pips),
        "type_counts": dict(types),
        "efficiency": efficiency,
        "impact": impact,
        "average_playability": average_playability,
        "score": score,
        "bracket": bracket,
        "bracket_reasons": reasons,
        "top_synergies": edges,
        "keepable_hand_pct": keepable,
    }


def _estimate_bracket(cards: list[dict], lift_hits: int) -> tuple[int, list[str]]:
    reasons: list[str] = []
    bracket = 2  # core / precon-ish baseline
    for c in cards:
        text = (c.get("oracle_text") or "").lower() + " " + c.get("name", "").lower()
        for label, needles in _BRACKET_FLAGS.items():
            if any(n in text for n in needles) and label not in reasons:
                reasons.append(label)
    if "fast mana" in reasons:
        bracket = max(bracket, 3)
    if "extra turns" in reasons or "mass land denial" in reasons:
        bracket = max(bracket, 4)
    if lift_hits >= 1:
        bracket = max(bracket, 3)
        reasons.append(f"{lift_hits} flagged synergy/combo pair(s)")
    return bracket, reasons


def _p_at_least_k(successes: int, deck: int, draws: int, k: int) -> float:
    if successes <= 0 or deck <= 0:
        return 0.0
    draws = min(draws, deck)
    total = math.comb(deck, draws)
    if not total:
        return 0.0
    p = 0.0
    for i in range(k, draws + 1):
        if i > successes or (draws - i) > (deck - successes):
            continue
        p += math.comb(successes, i) * math.comb(deck - successes, draws - i) / total
    return round(p * 100, 1)
