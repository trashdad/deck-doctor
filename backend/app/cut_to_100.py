"""Cut to 100 — role- and curve-aware cut ranking (UX plan 2026-11-05 §4.5 / §6).

`suggest_cuts` (doctor.py) ranks nonland cards purely by their synergy/inclusion
contribution. This module layers the deck's *plan* on top of that ranking:

  * role quotas come from the active template (doctor.TEMPLATE keys: land / ramp /
    card_draw / removal / board_wipe; everything else is the uncapped "utility" pool
    whose implicit quota is 99 − sum(template), exactly as templates.py documents);
  * the mana curve is compared to the same idealised EDH shape diagnosis.py grades
    against (CURVE_IDEAL below is that dict, unchanged);
  * cuts are chosen greedily, one at a time, re-counting roles and curve bins after
    every pick, so N cuts never drain a role below its quota while any other legal
    cut exists. When only quota-breaking cuts remain they are still proposed, but
    flagged (`breaks_quota=True`) with the reason saying so.

The commander and every member of a complete combo / asserted engine are never
proposed (the latter inherited from suggest_cuts). Deterministic; no DB writes.
"""

from __future__ import annotations

from collections import Counter

from .doctor import DECK_SIZE, TEMPLATE, category_of, suggest_cuts
from .store import Store

# Ideal share of nonland spells per CMC bin (0,1,2,3,4,5,6+) — diagnosis._curve_score.
CURVE_IDEAL = {0: 0.05, 1: 0.13, 2: 0.22, 3: 0.22, 4: 0.16, 5: 0.11, 6: 0.11}
CURVE_TOP_BIN = 6

# Ranking weights. `contribution` is in [0, 1]; the role and curve terms are each
# normalised to [0, 1] before weighting, so a card in a role 50 % over quota earns
# at most ROLE_W of "cut priority" on top of its own weakness.
ROLE_W = 0.15
CURVE_W = 0.10

UTILITY = "utility"
_ROLE_LABEL = {
    "land": "Lands", "ramp": "Ramp", "card_draw": "Card Draw", "removal": "Removal",
    "board_wipe": "Board Wipes", UTILITY: "Utility",
}


def _role_of(card: dict, template: dict) -> str:
    """Template quota key for a card, or UTILITY for everything the template does not cap."""
    cat = category_of(card)
    return cat if cat in template else UTILITY


def _curve_bin(card: dict) -> int:
    cmc = card.get("cmc")
    cmc = float(cmc) if isinstance(cmc, (int, float)) else 0.0
    return min(int(cmc), CURVE_TOP_BIN)


def _is_basic(card: dict) -> bool:
    return "Basic" in (card.get("type_line") or "")


def cut_to_100(store: Store, commander_id: str, deck_ids: list[str],
               template: dict | None = None, target: int | None = None) -> dict:
    """Propose exactly `target` cuts (default: however many cards the deck is over 100).

    `deck_ids` is the 99-side list (the commander may appear; it is ignored) and may
    contain repeated ids (basic lands). Returns::

        {"over_by": int, "target": int, "cuts": [cut, ...], "shortfall": int,
         "roles_before": {role: count}, "roles_after": {role: count}, "quotas": {role: n}}

    Each cut carries the suggest_cuts `contribution` + `reasons`, plus `role`,
    `role_before`, `role_after`, `quota`, `curve_bin`, `curve_before`, `curve_after`,
    `curve_ideal`, `breaks_quota` and a one-sentence `reason` with the evidence.
    `shortfall` > 0 means fewer than `target` cuts were legal at all (everything else
    is the commander or a protected combo piece).
    """
    tpl = {**TEMPLATE, **(template or {})}
    deck = [cid for cid in deck_ids if cid != commander_id]
    size = 1 + len(deck)
    over_by = size - DECK_SIZE
    n = over_by if target is None else target
    n = max(n, 0)

    # Utility is the uncapped overflow pool (templates.py: 99 − sum(counts)); it has
    # no floor, so a utility cut never "breaks quota" and earns no surplus bonus.
    quotas = {k: int(v) for k, v in tpl.items()}
    quotas[UTILITY] = 0

    # Live state the greedy loop mutates: role counts, curve bins, remaining copies.
    roles: Counter[str] = Counter()
    curve: Counter[int] = Counter()
    copies: Counter[str] = Counter()
    cards: dict[str, dict] = {}
    for cid in deck:
        card = store.get(cid)
        if card is None:
            continue
        cards[cid] = card
        copies[cid] += 1
        roles[_role_of(card, tpl)] += 1
        if category_of(card) != "land":
            curve[_curve_bin(card)] += 1
    roles_before = {r: roles[r] for r in _ROLE_LABEL}

    # Weakness scores. Nonlands: suggest_cuts (already excludes commander, lands and
    # protected combo/engine members). Lands: staple popularity only; basics are
    # interchangeable so they rank as the cheapest land cut.
    base: dict[str, dict] = {}
    for c in suggest_cuts(store, commander_id, deck, limit=len(deck) + 1):
        base.setdefault(c["card_id"], c)
    for cid, card in cards.items():
        if category_of(card) != "land" or cid in base:
            continue
        if _is_basic(card):
            base[cid] = {"card_id": cid, "contribution": 0.0, "reasons": [
                {"signal": "basic", "value": 0.0,
                 "detail": "basic land (interchangeable)"}]}
        else:
            staple = max(0.0, min(1.0, store.staple_score(cid)))
            base[cid] = {"card_id": cid, "contribution": round(staple, 6), "reasons": [
                {"signal": "staple", "value": round(staple, 4),
                 "detail": "corpus staple (1.0 = the most-played card)"}]}

    def ideal_for(b: int) -> float:
        """Ideal card count for a bin at the deck's *current* nonland size (as
        diagnosis._curve_score compares shares, not a fixed 62-card target)."""
        return CURVE_IDEAL[b] * sum(curve.values())

    def priority(cid: str) -> tuple:
        """Lower sorts first = cut sooner. (breaks_quota, weighted score, id).

        Surplus terms are x / (x + reference): 0 when nothing is over, → 1 as the
        overflow dwarfs the quota/ideal, and never saturating, so Removal 3/1 still
        outranks Card Draw 2/1."""
        card = cards[cid]
        role = _role_of(card, tpl)
        quota = quotas[role]
        breaks = role != UTILITY and roles[role] - 1 < quota
        surplus = max(roles[role] - quota, 0)
        role_term = surplus / (surplus + quota) if role != UTILITY and surplus else 0.0
        curve_term = 0.0
        if category_of(card) != "land":
            b = _curve_bin(card)
            ideal = ideal_for(b)
            overload = max(curve[b] - ideal, 0.0)
            curve_term = overload / (overload + ideal) if overload else 0.0
        score = base[cid]["contribution"] - ROLE_W * role_term - CURVE_W * curve_term
        return (breaks, score, cid)

    cuts: list[dict] = []
    while len(cuts) < n:
        pool = [cid for cid in base if copies[cid] > 0]
        if not pool:
            break
        pool.sort(key=priority)
        cid = pool[0]
        card = cards[cid]
        role = _role_of(card, tpl)
        quota = quotas[role]
        before = roles[role]
        after = before - 1
        breaks = role != UTILITY and after < quota
        is_land = category_of(card) == "land"
        b = None if is_land else _curve_bin(card)
        c_before = curve[b] if b is not None else None
        c_after = c_before - 1 if c_before is not None else None
        c_ideal = round(ideal_for(b), 1) if b is not None else None

        cuts.append({
            **base[cid],
            "role": role, "role_before": before, "role_after": after, "quota": quota,
            "quota_after": after,
            "curve_bin": b, "curve_before": c_before, "curve_after": c_after,
            "curve_ideal": c_ideal, "breaks_quota": breaks,
            "reason": _sentence(card, role, before, after, quota, breaks,
                                b, c_before, c_after, c_ideal, base[cid]["reasons"]),
        })
        copies[cid] -= 1
        roles[role] -= 1
        if b is not None:
            curve[b] -= 1

    return {
        "over_by": over_by, "target": n, "cuts": cuts, "shortfall": n - len(cuts),
        "roles_before": roles_before, "roles_after": {r: roles[r] for r in _ROLE_LABEL},
        "quotas": quotas,
    }


def _sentence(card: dict, role: str, before: int, after: int, quota: int, breaks: bool,
              b: int | None, c_before: int | None, c_after: int | None,
              c_ideal: float | None, reasons: list[dict]) -> str:
    label = _ROLE_LABEL[role]
    if role == UTILITY:
        role_txt = f"{label} {before} → {after} (uncapped)"
    elif breaks:
        role_txt = (f"cutting it drops {label} to {after}, below the template's {quota}"
                    " (nothing else is left to cut)")
    else:
        role_txt = f"{label} {before} → {after} stays at or above the template's {quota}"

    if b is not None:
        bin_name = f"{b}+" if b == CURVE_TOP_BIN else str(b)
        rel = "was over" if c_before > (c_ideal or 0) else "was within"
        curve_txt = (f"cmc {bin_name}: that bin goes {c_before} → {c_after}"
                     f" ({rel} the ideal {c_ideal} before the cut)")
    else:
        curve_txt = "a land, so the curve is unchanged"

    by_signal = {r["signal"]: r for r in reasons}
    if "basic" in by_signal:
        weak_txt = "basic lands are interchangeable"
    elif "edhrec" in by_signal:
        weak_txt = by_signal["edhrec"]["detail"]
        if "cooccurrence" in by_signal:
            weak_txt += f"; {by_signal['cooccurrence']['detail']}"
    elif "staple" in by_signal:
        weak_txt = f"staple score {by_signal['staple']['value']:.2f}"
        if "synergy" in by_signal:
            weak_txt += f"; {by_signal['synergy']['detail']}"
    elif "synergy" in by_signal:
        weak_txt = by_signal["synergy"]["detail"]
        if "cooccurrence" in by_signal:
            weak_txt += f"; {by_signal['cooccurrence']['detail']}"
    else:
        weak_txt = "no synergy or popularity signal"
    return f"{card.get('name', '?')}: {weak_txt}; {role_txt}; {curve_txt}."
