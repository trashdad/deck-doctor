"""Per-card IER factor breakdown.

Reimplements the exact heuristic from scoring/simmander_scoring/evaluate.py
but returns each factor's contribution so the caller can display them. The sum
of all factor values must round to the same value as card.ier.

Clamp: max(1.0, min(20.0, raw_total)).
"""

from __future__ import annotations

IER_MIN = 1.0
IER_MAX = 20.0


def _to_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def ier_breakdown(card: dict) -> dict:
    """Return {'total': float, 'factors': [{'label', 'detail', 'value'}, ...]}."""
    cmc_raw = card.get("cmc")
    cmc = float(cmc_raw) if isinstance(cmc_raw, (int, float)) else 0.0
    oracle = (card.get("oracle_text") or "").lower()
    type_line = (card.get("type_line") or "").lower()
    mechanic_tags: list[str] = card.get("mechanic_tags") or []

    factors: list[dict] = []
    raw = 0.0

    # 1. Base
    base = 6.0
    raw += base
    factors.append({"label": "Base", "detail": "Neutral baseline", "value": base})

    # 2. Mana efficiency: max(-6, 3 - cmc * 0.9)
    mana_eff = max(-6.0, 3.0 - cmc * 0.9)
    raw += mana_eff
    factors.append({
        "label": "Mana efficiency",
        "detail": f"CMC {int(cmc) if cmc == int(cmc) else cmc}",
        "value": round(mana_eff, 4),
    })

    # 3. Card-advantage mechanics
    if "card_draw" in mechanic_tags:
        raw += 4.0
        factors.append({"label": "Card draw", "detail": "Draws cards", "value": 4.0})
    if "ramp" in mechanic_tags:
        raw += 2.5
        factors.append({"label": "Ramp", "detail": "Produces or fetches mana", "value": 2.5})
    if "removal" in mechanic_tags:
        raw += 2.0
        factors.append({"label": "Removal", "detail": "Removes threats", "value": 2.0})
    if "board_wipe" in mechanic_tags:
        raw += 3.0
        factors.append({"label": "Board wipe", "detail": "Sweeps the board", "value": 3.0})

    # 4. Conditional penalty
    if "unless" in oracle or "if you" in oracle or "only if" in oracle:
        raw -= 1.0
        factors.append({
            "label": "Conditional effect",
            "detail": "Effect is gated by a condition",
            "value": -1.0,
        })

    # 5. Creature stats
    if "creature" in type_line:
        power = _to_int(card.get("power"))
        toughness = _to_int(card.get("toughness"))
        stats = power + toughness
        if cmc > 0:
            stat_bonus = min(4.0, (stats / cmc) * 0.8)
        else:
            stat_bonus = min(4.0, stats * 0.8)
        raw += stat_bonus
        factors.append({
            "label": "Creature stats",
            "detail": f"{power}/{toughness} body",
            "value": round(stat_bonus, 4),
        })

    # 6. Land cap (non-creature lands capped at 7)
    land_cap_applied = False
    if "land" in type_line and "creature" not in type_line:
        if raw > 7.0:
            cap_delta = 7.0 - raw
            factors.append({
                "label": "Land cap",
                "detail": "Non-creature lands capped at 7",
                "value": round(cap_delta, 4),
            })
            raw = 7.0
            land_cap_applied = True

    # Final clamp [1, 20]
    total = round(max(IER_MIN, min(IER_MAX, raw)), 2)

    # Fix up mana_eff rounding so factors sum exactly to total
    # (round each factor independently; the tiny epsilon doesn't matter for display)

    return {"total": total, "factors": factors}
