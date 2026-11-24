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

The commander, any partner / background in the command zone, and every member of a
complete combo / asserted engine (lands included) are never proposed. A card whose
front face is a spell and back face a land ('Sorcery // Land') is ranked as the spell.
Deterministic; no DB writes.
"""

from __future__ import annotations

import math
from collections import Counter

from .doctor import DECK_SIZE, TEMPLATE, category_of, suggest_cuts
from .store import Store

# Ideal share of nonland spells per CMC bin (0,1,2,3,4,5,6+) — diagnosis._curve_score.
CURVE_IDEAL = {0: 0.05, 1: 0.13, 2: 0.22, 3: 0.22, 4: 0.16, 5: 0.11, 6: 0.11}
CURVE_TOP_BIN = 6

# Ranking weights. `contribution` is in [0, 1]; the role and curve terms are each
# normalised to [0, 1] before weighting, so a card in a role 50 % over quota earns
# at most ROLE_W of "cut priority" on top of its own weakness.
#
# Backtested 2026-11-24 (docs/plans/2026-11-24-ranking-eval.md, tools/eval/backtest_cuts.py:
# plant 3-8 known-bad cards in 600 real corpus decks and measure recall@k of the cuts;
# commander-disjoint 70/30 split). Against ROLE_W = CURVE_W = 0, these terms cut 3.5-4.4x
# fewer cards that >= 50 % of the commander's EDHREC decks run, in both intruder
# regimes. Recall@k goes up when the planted cards are plausible corpus-played cards
# (0.23 -> 0.31) and down when they are arbitrary legal cards (0.45 -> 0.40). On the 9x9
# train grid, no setting beat (0.15, 0.10) in both regimes without more damaging cuts.
# The values are therefore kept; whether another value is better for real decks is UNKNOWN.
ROLE_W = 0.15
CURVE_W = 0.10

UTILITY = "utility"
_ROLE_LABEL = {
    "land": "Lands", "ramp": "Ramp", "card_draw": "Card Draw", "removal": "Removal",
    "board_wipe": "Board Wipes", UTILITY: "Utility",
}


def validate_template(template: dict | None) -> None:
    """Raise ValueError naming any key that is not one of doctor.TEMPLATE's roles.

    category_of also yields counters / tokens / synergy, but those are not quota roles
    (templates.py presets only ever send the five TEMPLATE keys)."""
    bad = sorted(set(template or {}) - set(TEMPLATE))
    if bad:
        raise ValueError(f"unknown template role(s) {', '.join(bad)}; "
                         f"allowed: {', '.join(TEMPLATE)}")


def _front_face(card: dict) -> dict:
    """The card as cut_to_100 ranks it: a multi-face card whose FRONT face is not a land
    (e.g. 'Sorcery // Land' MDFCs, 'Enchantment // Land' transforms) is a spell, so its
    type_line is narrowed to the front face. doctor.category_of is left untouched."""
    tl = card.get("type_line") or ""
    if "//" not in tl or "Land" not in tl:
        return card
    faces = card.get("card_faces") or []
    front = (faces[0].get("type_line") if faces and isinstance(faces[0], dict) else None) \
        or tl.split("//", 1)[0].strip()
    if "Land" in front:
        return card
    return {**card, "type_line": front}


class _FrontFaceStore:
    """Store view whose get() returns _front_face(card), so suggest_cuts scores a
    spell-with-a-land-back as the spell it is cast as. Everything else delegates."""

    def __init__(self, store):
        self._store = store

    def get(self, cid):
        card = self._store.get(cid)
        return None if card is None else _front_face(card)

    def __getattr__(self, name):
        return getattr(self._store, name)


def _role_of(card: dict, template: dict) -> str:
    """Template quota key for a card, or UTILITY for everything the template does not cap."""
    cat = category_of(card)
    return cat if cat in template else UTILITY


def _curve_bin(card: dict) -> int:
    """CMC bin 0..CURVE_TOP_BIN. Non-numeric, NaN and negative cmc → 0; +inf → top bin."""
    cmc = card.get("cmc")
    if isinstance(cmc, bool) or not isinstance(cmc, (int, float)):
        return 0
    cmc = float(cmc)
    if math.isnan(cmc) or cmc <= 0:
        return 0
    if cmc >= CURVE_TOP_BIN:
        return CURVE_TOP_BIN
    return int(cmc)


def _is_basic(card: dict) -> bool:
    return "Basic" in (card.get("type_line") or "")


def _protected_ids(store, deckset: set[str]) -> set[str]:
    """Every member of a complete combo / asserted engine within the deck — computed
    here, not inherited from suggest_cuts, because suggest_cuts skips lands before its
    own protected set is consulted (a land combo piece would otherwise be cuttable)."""
    protected: set[str] = set()
    ids = sorted(deckset)
    for combo in store.deck_spellbook(ids).get("complete") or []:
        protected.update(combo.get("members") or [])
    for eng in store.deck_engines(ids).get("combos") or []:
        protected.update(eng.get("members") or [])
    return protected


def cut_to_100(store: Store, commander_id: str, deck_ids: list[str],
               template: dict | None = None, target: int | None = None,
               role_w: float | None = None, curve_w: float | None = None,
               partner_ids: list[str] | None = None) -> dict:
    """Propose exactly `target` cuts (default: however many cards the deck is over 100).

    `role_w` / `curve_w` override ROLE_W / CURVE_W (used by the offline backtest,
    tools/eval/backtest_cuts.py); None means the module constants.

    `deck_ids` is the 99-side list (the commander may appear; it is ignored) and may
    contain repeated ids (basic lands). `partner_ids` are other command-zone cards
    (partner, background): they count toward 100 and are never proposed. Ids the
    store does not know count toward nothing and are listed in `unknown_ids`.
    `template` keys must be doctor.TEMPLATE roles (ValueError otherwise). Returns::

        {"over_by": int, "target": int, "cuts": [cut, ...], "shortfall": int,
         "roles_before": {role: count}, "roles_after": {role: count}, "quotas": {role: n},
         "unknown_ids": [id, ...]}

    Each cut carries the suggest_cuts `contribution` + `reasons`, plus `role`,
    `role_before`, `role_after`, `quota`, `curve_bin`, `curve_before`, `curve_after`,
    `curve_ideal`, `breaks_quota` and a one-sentence `reason` with the evidence.
    `shortfall` > 0 means fewer than `target` cuts were legal at all (everything else
    is a commander or a protected combo piece).
    """
    validate_template(template)
    rw = ROLE_W if role_w is None else float(role_w)
    cw = CURVE_W if curve_w is None else float(curve_w)
    tpl = {**TEMPLATE, **(template or {})}
    view = _FrontFaceStore(store)
    command = {commander_id}
    unknown: list[str] = []
    partners: list[str] = []
    for pid in dict.fromkeys(partner_ids or []):
        if pid in command:
            continue
        if store.get(pid) is None:
            unknown.append(pid)
        else:
            partners.append(pid)
            command.add(pid)
    deck: list[str] = []
    cards: dict[str, dict] = {}
    for cid in deck_ids:
        if cid in command:
            continue
        card = cards[cid] if cid in cards else view.get(cid)
        if card is None:
            if cid not in unknown:
                unknown.append(cid)
            continue
        cards[cid] = card
        deck.append(cid)
    size = 1 + len(partners) + len(deck)
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
    for cid in deck:
        card = cards[cid]
        copies[cid] += 1
        roles[_role_of(card, tpl)] += 1
        if category_of(card) != "land":
            curve[_curve_bin(card)] += 1
    roles_before = {r: roles[r] for r in _ROLE_LABEL}

    # Never proposed: the commander(s) and every combo / engine member (lands too).
    protected = command | _protected_ids(store, set(deck) | command)

    # Weakness scores. Nonlands: suggest_cuts (partners passed as deck cards so their
    # co-play still counts for the others). Lands: staple popularity only; basics are
    # interchangeable so they rank as the cheapest land cut.
    base: dict[str, dict] = {}
    scored = deck + partners
    for c in suggest_cuts(view, commander_id, scored, limit=len(scored) + 1):
        if c["card_id"] not in protected:
            base.setdefault(c["card_id"], c)
    for cid, card in cards.items():
        if category_of(card) != "land" or cid in base or cid in protected:
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
        score = base[cid]["contribution"] - rw * role_term - cw * curve_term
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
        "quotas": quotas, "unknown_ids": unknown,
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
