"""SP5 — commander-based suggestion engine.

Online, read-time blend over the prebuilt tables (no offline build of its own):

    score(c) = w_edh    * edhrec_synergy(cmd, c)
             + w_cooc   * mean liftnorm(c, d) over deck members d
             + w_struct * mean synergy(c, d) over deck members d
             + w_engine * engine_completion(c, deck)

The means are computed by ACCUMULATION: one pass over each deck member's indexed
neighbor list adds that member's contribution to the candidate's running sum, and
the sum is divided by |deck| at the end. Missing pairs contribute 0 — identical
math to the spec's mean(), but O(|deck| * K) instead of O(|deck|^2 * K) queries.

Cold-start tiers when the commander has no EDHREC rows:
  1. "edhrec"        — full blend.
  2. "cooccurrence"  — w_edh dropped; candidates seeded from the commander's own
                       neighbors plus deck-card neighbors.
  3. "color_staple"  — too few candidates: fill from color-identity-filtered top
                       deck-frequency cards, clearly labeled as a generic fallback.
"""

from __future__ import annotations

import math
from collections import defaultdict

from .store import Store

# Blend weights (hand-tuned vs. the golden tests; learned weights are a non-goal).
WEIGHTS = {"edh": 0.45, "cooc": 0.30, "struct": 0.15, "engine": 0.10}
NEIGHBOR_K = 30          # neighbors pulled per deck member per signal
ENGINE_BONUS_ASSERTED = 1.0
ENGINE_BONUS_CANDIDATE = 0.3
STAPLE_SCORE = 0.05      # below any signal-driven score; staples are a last resort

# Mirror of scoring/cooccurrence/fuse.py::lift_to_norm (backend must not import scoring/).
LIFT_K = 0.25

# Commander banlist (cards.json carries no legalities). Extensible static set.
BANLIST = frozenset({
    "Ancestral Recall", "Balance", "Biorhythm", "Black Lotus", "Channel",
    "Chaos Orb", "Dockside Extortionist", "Emrakul, the Aeons Torn",
    "Erayo, Soratami Ascendant", "Falling Star", "Fastbond", "Flash",
    "Golos, Tireless Pilgrim", "Griselbrand", "Hullbreacher",
    "Iona, Shield of Emeria", "Jeweled Lotus", "Karakas", "Leovold, Emissary of Trest",
    "Library of Alexandria", "Limited Resources", "Lutri, the Spellchaser",
    "Mana Crypt", "Mox Emerald", "Mox Jet", "Mox Pearl", "Mox Ruby", "Mox Sapphire",
    "Nadu, Winged Wisdom", "Paradox Engine", "Primeval Titan", "Prophet of Kruphix",
    "Recurring Nightmare", "Rofellos, Llanowar Emissary", "Shahrazad",
    "Sundering Titan", "Sway of the Stars", "Sylvan Primordial", "Time Vault",
    "Time Walk", "Tinker", "Tolarian Academy", "Trade Secrets", "Upheaval",
    "Yawgmoth's Bargain",
})


def lift_to_norm(lift: float) -> float:
    """Map raw lift in [0, inf) to [0, 1): 0 when lift <= 1 (no positive association)."""
    if lift <= 1.0:
        return 0.0
    return min(1.0 - math.exp(-LIFT_K * (lift - 1.0)), 0.999999)


def is_commander(card: dict | None) -> bool:
    tl = (card or {}).get("type_line") or ""
    return "Legendary" in tl and ("Creature" in tl or "Planeswalker" in tl)


def _suggestable(card: dict, ci: set[str]) -> bool:
    if card["name"] in BANLIST:
        return False
    if "Basic" in (card.get("type_line") or ""):
        return False
    return set(card.get("color_identity") or []) <= ci


def recommend(store: Store, commander_id: str, deck_ids: list[str],
              limit: int = 12, explain: bool = False) -> dict:
    """Rank the best next cards for the commander + partial deck. See module docstring."""
    cmd = store.get(commander_id)
    ci = set(cmd.get("color_identity") or [])
    cmd_name = cmd.get("name", "")
    deck_set = set(deck_ids) | {commander_id}
    members = sorted(deck_set)            # commander counts as a deck member
    n = len(members)

    acc: dict[str, dict] = defaultdict(lambda: {
        "edh": 0.0, "cooc": 0.0, "struct": 0.0, "engine": 0.0,
        "cooc_hits": 0, "struct_hits": 0, "engine_with": None,
    })

    edh = store.edhrec_for(commander_id)
    tier = "edhrec" if edh else "cooccurrence"
    for cid, (synergy, _inclusion) in edh.items():
        acc[cid]["edh"] = max(0.0, min(1.0, synergy))

    for d in members:
        for other, lift, _jac in store.cooccurrence_neighbors(d, NEIGHBOR_K):
            a = acc[other]
            a["cooc"] += lift_to_norm(lift)
            a["cooc_hits"] += 1
        for other, synergy in store.synergy_neighbors(d, NEIGHBOR_K):
            a = acc[other]
            a["struct"] += synergy
            a["struct_hits"] += 1
        for eng in store.engines_with(d):
            missing = [m for m in eng["members"] if m not in deck_set]
            if len(missing) != 1:
                continue
            a = acc[missing[0]]
            bonus = ENGINE_BONUS_ASSERTED if eng["asserted"] else ENGINE_BONUS_CANDIDATE
            if bonus > a["engine"]:
                a["engine"] = bonus
                a["engine_with"] = eng

    weights = dict(WEIGHTS)
    if not edh:
        weights["edh"] = 0.0
    total_w = sum(weights.values())

    scored: list[tuple[float, str, dict]] = []
    for cid, a in acc.items():
        if cid in deck_set:
            continue
        card = store.get(cid)
        if card is None or not _suggestable(card, ci):
            continue
        score = (weights["edh"] * a["edh"]
                 + weights["cooc"] * (a["cooc"] / n)
                 + weights["struct"] * (a["struct"] / n)
                 + weights["engine"] * a["engine"]) / total_w
        if score <= 0.0:
            continue
        scored.append((score, cid, a))
    scored.sort(key=lambda t: (-t[0], t[1]))
    scored = scored[: max(limit, 0)]

    # Tier 3: not enough signal-driven candidates — fill with format staples in-colors.
    staple_fill: list[tuple[float, str, dict]] = []
    if len(scored) < limit:
        if not scored:
            tier = "color_staple"
        have = {cid for _, cid, _ in scored}
        top_freq = None
        for cid, freq in store.staples_for_colors(ci, limit=limit * 3, exclude=deck_set | have):
            card = store.get(cid)
            if card is None or card["name"] in BANLIST:
                continue
            top_freq = top_freq or max(freq, 1)
            staple_fill.append((STAPLE_SCORE * freq / top_freq, cid,
                                {"staple_freq": freq}))
            if len(scored) + len(staple_fill) >= limit:
                break

    suggestions = []
    for score, cid, a in scored:
        entry = {"card": store.get(cid), "score": round(score, 6), "reasons": []}
        if explain:
            entry["reasons"] = _reasons(store, a, n, cmd_name)
        suggestions.append(entry)
    for score, cid, a in staple_fill:
        entry = {"card": store.get(cid), "score": round(score, 6), "reasons": []}
        if explain:
            entry["reasons"] = [{
                "signal": "staple", "value": round(score, 6),
                "detail": "format staple in your colors (generic fallback)",
            }]
        suggestions.append(entry)

    return {"tier": tier, "suggestions": suggestions}


def _reasons(store: Store, a: dict, n: int, cmd_name: str) -> list[dict]:
    out: list[dict] = []
    if a["edh"] > 0:
        out.append({"signal": "edhrec", "value": round(a["edh"], 4),
                    "detail": f"EDHREC synergy with {cmd_name}"})
    if a["cooc"] > 0:
        out.append({"signal": "cooccurrence", "value": round(a["cooc"] / n, 4),
                    "detail": f"played alongside {a['cooc_hits']} of your cards"})
    if a["struct"] > 0:
        out.append({"signal": "synergy", "value": round(a["struct"] / n, 4),
                    "detail": f"mechanical synergy with {a['struct_hits']} of your cards"})
    if a["engine"] > 0 and a["engine_with"] is not None:
        eng = a["engine_with"]
        names = [(store.get(m) or {}).get("name", m) for m in eng["members"]]
        kind = "combo" if eng["asserted"] else f"{eng['kind']} engine"
        out.append({"signal": "engine", "value": round(a["engine"], 4),
                    "detail": f"completes {kind}: {' + '.join(names)}"})
    return out
