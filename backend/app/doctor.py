"""SP8 — Deck Doctor: type-aware deck completion + cut suggestions.

`category_of` is the FINAL server-side mirror of frontend zones.ts::autoZone, shared
by SP6 import zoning and SP9 graph nodes. complete_deck() fills a deck to 100 with a
quota-aware greedy + pip-ratio basics; suggest_cuts() ranks the weakest cards by their
synergy contribution to the rest of the deck. Both are deterministic (no randomness).
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

from .store import Store
from .suggest import (BANLIST, NEIGHBOR_K, WEIGHTS, lift_to_norm, recommend)

CATEGORIES = ("commander", "land", "ramp", "card_draw", "removal",
              "board_wipe", "counters", "tokens", "synergy")

TEMPLATE = {
    "land": 37, "ramp": 10, "card_draw": 10, "removal": 9, "board_wipe": 3,
}
NONBASIC_LAND_CAP = 12
RESCORE_EVERY = 10
DECK_SIZE = 100
DEFICIT_BOOST = 1.5

ZONE_FOR_CATEGORY = {
    "land": "Lands", "ramp": "Ramp", "card_draw": "Card Draw", "removal": "Removal",
    "board_wipe": "Board Wipes", "counters": "Counters", "tokens": "Tokens",
    "synergy": "Utility",
}

BASIC_FOR_COLOR = {"W": "Plains", "U": "Island", "B": "Swamp",
                   "R": "Mountain", "G": "Forest"}
_WUBRG = ["W", "U", "B", "R", "G"]
_PIP = re.compile(r"\{([WUBRG])(?:/[WUBRGP])?\}")


def category_of(card: dict) -> str:
    """Server-side mirror of frontend zones.ts::autoZone. FINAL — do not change."""
    tl = card.get("type_line") or ""
    tags = card.get("mechanic_tags") or []
    if "Land" in tl:
        return "land"
    if "board_wipe" in tags:
        return "board_wipe"
    if "removal" in tags:
        return "removal"
    if "ramp" in tags:
        return "ramp"
    if "card_draw" in tags:
        return "card_draw"
    if any(t.startswith("counter_") for t in tags):
        return "counters"
    if any(t.startswith("token_") for t in tags):
        return "tokens"
    return "synergy"


def _zone(category: str) -> str:
    return ZONE_FOR_CATEGORY.get(category, "Utility")


def complete_deck(store: Store, commander_id: str, deck_ids: list[str],
                  template: dict = TEMPLATE) -> dict:
    """Deterministically fill the deck toward a 100-card template. See module docstring."""
    cmd = store.get(commander_id)
    ci = set(cmd.get("color_identity") or [])
    present: set[str] = set(deck_ids) | {commander_id}
    counts: Counter[str] = Counter()
    for cid in deck_ids:
        c = store.get(cid)
        if c:
            counts[category_of(c)] += 1

    added: list[dict] = []
    nonland_target = DECK_SIZE - 1 - template["land"]   # 62

    def nonland_count() -> int:
        return sum(v for k, v in counts.items() if k != "land")

    def capped(cat: str) -> bool:
        # Quota categories are capped at their template; "synergy" is the uncapped overflow.
        return cat in template and counts[cat] >= template[cat]

    pool: list[tuple[float, dict]] = []

    def refresh_pool() -> None:
        nonlocal pool
        cur = [c for c in present if c != commander_id]
        recs = recommend(store, commander_id, cur, limit=120, explain=False)["suggestions"]
        pool = [(r["score"], r["card"]) for r in recs
                if r["card"]["id"] not in present and category_of(r["card"]) != "land"]

    refresh_pool()
    since_refresh = 0
    staple_iter = None

    while nonland_count() < nonland_target:
        pool = [(s, c) for (s, c) in pool
                if c["id"] not in present and not capped(category_of(c))]
        chosen: dict | None = None
        from_staple = False
        if pool:
            def boosted(item: tuple[float, dict]) -> float:
                s, c = item
                cat = category_of(c)
                deficit = max(template.get(cat, 0) - counts[cat], 0)
                return s * (DEFICIT_BOOST if deficit > 0 else 1.0)

            pool.sort(key=lambda it: (-boosted(it), it[1]["id"]))
            chosen = pool[0][1]
        else:
            if staple_iter is None:
                staple_iter = iter(store.staples_for_colors(ci, limit=400, exclude=present))
            while chosen is None:
                nxt = next(staple_iter, None)
                if nxt is None:
                    break
                cid, _freq = nxt
                card = store.get(cid)
                if (card is None or cid in present or category_of(card) == "land"
                        or card["name"] in BANLIST or capped(category_of(card))):
                    continue
                chosen = card
                from_staple = True
            if chosen is None:
                break   # nothing left to add

        cat = category_of(chosen)
        deficit_before = max(template.get(cat, 0) - counts[cat], 0)
        if from_staple:
            reason = "staple fill"
        elif deficit_before > 0:
            reason = f"{cat.replace('_', ' ')} (deficit fill)"
        else:
            reason = "best blend score"
        added.append({"card_id": chosen["id"], "zone": _zone(cat),
                      "quantity": 1, "reason": reason})
        present.add(chosen["id"])
        counts[cat] += 1
        since_refresh += 1
        if since_refresh >= RESCORE_EVERY:
            refresh_pool()
            since_refresh = 0

    _add_lands(store, ci, present, counts, added, template)

    final_size = 1 + len(deck_ids) + sum(a["quantity"] for a in added)
    return {"added": added, "final_size": final_size}


def _add_lands(store: Store, ci: set[str], present: set[str], counts: Counter,
               added: list[dict], template: dict) -> None:
    land_deficit = max(template["land"] - counts["land"], 0)
    if land_deficit <= 0:
        return

    # (a) nonbasic land staples in colour identity.
    nonbasic_added = 0
    for cid, _freq in store.staples_for_colors(ci, limit=600, exclude=present):
        if nonbasic_added >= min(NONBASIC_LAND_CAP, land_deficit):
            break
        card = store.get(cid)
        if card is None or "Land" not in (card.get("type_line") or ""):
            continue
        if card["name"] in BANLIST:
            continue
        added.append({"card_id": cid, "zone": "Lands", "quantity": 1,
                      "reason": "land staple"})
        present.add(cid)
        nonbasic_added += 1

    # (b) basics by coloured-pip ratio of every nonland card now in the deck.
    basic_slots = land_deficit - nonbasic_added
    if basic_slots <= 0:
        return
    pips: Counter[str] = Counter()
    for cid in present:
        card = store.get(cid)
        if card is None or category_of(card) == "land":
            continue
        for sym in _PIP.findall(card.get("mana_cost") or ""):
            if sym in ci or not ci:
                pips[sym] += 1

    colorless = not ci or sum(pips.values()) == 0
    if colorless and not ci:
        _emit_basic(store, added, "Wastes", basic_slots)
        return

    if sum(pips.values()) == 0:
        # colored CI but no colored pips: split evenly across CI colors.
        colors = [c for c in _WUBRG if c in ci]
        for i, c in enumerate(colors):
            n = basic_slots // len(colors) + (1 if i < basic_slots % len(colors) else 0)
            if n:
                _emit_basic(store, added, BASIC_FOR_COLOR[c], n)
        return

    total = sum(pips.values())
    floors: dict[str, int] = {}
    fracs: list[tuple[float, str]] = []
    for c in _WUBRG:
        if pips.get(c, 0) == 0:
            continue
        exact = basic_slots * pips[c] / total
        floors[c] = int(exact)
        fracs.append((exact - int(exact), c))
    remainder = basic_slots - sum(floors.values())
    # distribute remainder by largest fractional part; ties broken by WUBRG order.
    fracs.sort(key=lambda t: (-t[0], _WUBRG.index(t[1])))
    for i in range(remainder):
        floors[fracs[i % len(fracs)][1]] = floors.get(fracs[i % len(fracs)][1], 0) + 1
    for c in _WUBRG:
        n = floors.get(c, 0)
        if n:
            _emit_basic(store, added, BASIC_FOR_COLOR[c], n)


def _emit_basic(store: Store, added: list[dict], name: str, qty: int) -> None:
    cid = store._name_to_id.get(name.lower())
    if cid is None or qty <= 0:
        return
    added.append({"card_id": cid, "zone": "Lands", "quantity": qty,
                  "reason": "basic land (pip ratio)"})


def suggest_cuts(store: Store, commander_id: str, deck_ids: list[str],
                 limit: int = 10) -> list[dict]:
    """Rank the weakest nonland cards by synergy contribution to the rest of the deck."""
    deck = [c for c in deck_ids if c != commander_id]
    deckset = set(deck) | {commander_id}
    members = sorted(deckset)
    n = len(members)
    denom = max(n - 1, 1)

    edh = store.edhrec_for(commander_id)
    cooc: dict[str, float] = defaultdict(float)
    cooc_hits: dict[str, int] = defaultdict(int)
    struct: dict[str, float] = defaultdict(float)
    struct_hits: dict[str, int] = defaultdict(int)
    for d in members:
        for other, lift, _jac in store.cooccurrence_neighbors(d, NEIGHBOR_K):
            if other in deckset and other != d:
                cooc[d] += lift_to_norm(lift)
                cooc_hits[d] += 1
        for other, synergy in store.synergy_neighbors(d, NEIGHBOR_K):
            if other in deckset and other != d:
                struct[d] += synergy
                struct_hits[d] += 1

    # Protect every member of a complete combo / asserted engine within the deck.
    protected: set[str] = set()
    sb = store.deck_spellbook(list(deckset))
    for combo in sb["complete"]:
        protected.update(combo["members"])
    eng = store.deck_engines(list(deckset))
    for e in eng["combos"]:
        protected.update(e["members"])

    total_w = sum(WEIGHTS.values())
    cuts: list[dict] = []
    for cid in deck:
        card = store.get(cid)
        if card is None or category_of(card) == "land" or cid in protected:
            continue
        edh_v = max(0.0, min(1.0, edh.get(cid, (0.0, 0.0))[0])) if edh else 0.0
        contrib = (WEIGHTS["edh"] * edh_v
                   + WEIGHTS["cooc"] * (cooc[cid] / denom)
                   + WEIGHTS["struct"] * (struct[cid] / denom)) / total_w
        reasons = []
        if edh:
            reasons.append({"signal": "edhrec", "value": round(edh_v, 4),
                            "detail": "EDHREC synergy with commander"})
        reasons.append({"signal": "cooccurrence", "value": round(cooc[cid] / denom, 4),
                        "detail": f"played with {cooc_hits[cid]} of your other cards"})
        reasons.append({"signal": "synergy", "value": round(struct[cid] / denom, 4),
                        "detail": f"mechanical synergy with {struct_hits[cid]} of your cards"})
        cuts.append({"card_id": cid, "contribution": round(contrib, 6), "reasons": reasons})

    cuts.sort(key=lambda x: (x["contribution"], x["card_id"]))
    return cuts[:limit]
