"""Deck templates + dual-theme composite suggestions.

Two things live here:

  * TEMPLATES — composition presets (land/ramp/card_draw/removal/board_wipe quotas).
    Both published expert presets (Command Zone + archetype variants) and a
    data-derived "Corpus Average", plus our editable "Simmander Composite". A
    selected template's `counts` flow straight into the Deck Doctor (complete_deck
    fills toward exactly those numbers) — the keys match doctor.TEMPLATE.

  * THEMES + theme_suggest() — each theme is a flat set of semantic tags; the
    suggestion pool is the union of the selected themes' cards. Cards matching
    BOTH chosen themes get a relevance boost (the dual-theme "bridge" payoff),
    then we rank by a blend of efficiency (IER) and commander synergy.

Pure read-time over the prebuilt store tables — no offline build, no inference.
"""

from __future__ import annotations

import re

from .store import Store
from .suggest import BANLIST, is_commander

# ---- Composition templates ------------------------------------------------
# `counts` keys mirror doctor.TEMPLATE exactly so the value drops into
# complete_deck() unchanged. synergy/utility = 99 − sum(counts) (uncapped).
TEMPLATES: list[dict] = [
    {"id": "command_zone", "name": "Command Zone", "source": "published",
     "counts": {"land": 38, "ramp": 10, "card_draw": 8, "removal": 8, "board_wipe": 4},
     "notes": "The famous 38/10/8/8/4 baseline."},
    {"id": "control", "name": "Control", "source": "published",
     "counts": {"land": 38, "ramp": 10, "card_draw": 10, "removal": 13, "board_wipe": 6},
     "notes": "More interaction + draw; fewer threats."},
    {"id": "aggro", "name": "Aggro", "source": "published",
     "counts": {"land": 35, "ramp": 8, "card_draw": 8, "removal": 6, "board_wipe": 2},
     "notes": "Lower curve; fewer lands + sweepers."},
    {"id": "combo", "name": "Combo", "source": "published",
     "counts": {"land": 36, "ramp": 11, "card_draw": 11, "removal": 6, "board_wipe": 2},
     "notes": "Dig + ramp to assemble the combo."},
    {"id": "corpus_average", "name": "Corpus Average", "source": "data-derived",
     "counts": {"land": 37, "ramp": 7, "card_draw": 9, "removal": 4, "board_wipe": 3},
     "notes": "Mean of 3,249 scraped decks ≥80 cards (lands normalized to 37)."},
    {"id": "simmander_composite", "name": "Simmander Composite", "source": "editable",
     "counts": {"land": 37, "ramp": 10, "card_draw": 9, "removal": 8, "board_wipe": 3},
     "notes": "Our default — edit the counts and pick two themes."},
]

# ---- Theme catalog (tags verified against the live tag inverted index) -----
# A couple of tags from the original design (t:landfall, t:token_created) are not
# in the built index; those themes fall back to the closest present tags so the
# pool is never empty.
THEMES: list[dict] = [
    {"id": "aristocrats", "label": "Aristocrats",
     "tags": ["e:sacrifice", "t:creature_dies", "e:lose_life", "cost:sacrifice"]},
    {"id": "landfall", "label": "Landfall / Lands", "tags": ["perm:land", "e:mana"]},
    {"id": "counters", "label": "+1/+1 Counters",
     "tags": ["c:plus1", "e:add_counter", "e:proliferate"]},
    {"id": "tokens", "label": "Tokens / Go-wide", "tags": ["e:create_token"]},
    {"id": "spellslinger", "label": "Spellslinger", "tags": ["t:cast_spell", "e:copy"]},
    {"id": "reanimator", "label": "Reanimator / Graveyard",
     "tags": ["e:reanimate", "e:mill", "e:discard"]},
    {"id": "lifegain", "label": "Lifegain", "tags": ["e:gain_life", "k:lifelink"]},
    {"id": "voltron", "label": "Voltron (auras / equip)",
     "tags": ["k:equip", "e:pump", "tgt:self"]},
    {"id": "blink", "label": "Blink / Flicker", "tags": ["e:bounce", "t:etb"]},
    {"id": "burn", "label": "Burn", "tags": ["e:damage"]},
    {"id": "mill", "label": "Mill", "tags": ["e:mill"]},
    {"id": "control", "label": "Control",
     "tags": ["e:counter_spell", "e:destroy", "e:board_wipe"]},
    {"id": "card_draw", "label": "Card Draw", "tags": ["e:draw"]},
    {"id": "ramp", "label": "Ramp", "tags": ["e:mana", "perm:land"]},
    {"id": "combat", "label": "Combat / Aggro",
     "tags": ["t:attacks", "t:combat_damage", "k:trample", "k:haste"]},
]

_THEMES_BY_ID = {t["id"]: t for t in THEMES}
IER_NORM_CAP = 20.0     # ier/20 → ~1.0 for the most efficient cards
SYN_NEIGHBOR_K = 3000   # structural neighbors pulled for the commander once


def _theme_card_ids(store: Store, theme: dict) -> set[str]:
    ids: set[str] = set()
    for tag in theme["tags"]:
        ids.update(store._tag_inverted.get(tag, []))
    return ids


def theme_suggest(store: Store, commander_id: str, theme_ids: list[str],
                  free_text: str = "", limit: int = 10, offset: int = 0) -> dict:
    """Rank cards in the union of the selected themes by efficiency × commander synergy.

    Returns {"cards": [{card, score, themes_matched}], "total", "has_more"}.
    Raises ValueError on a missing / non-commander id (the router maps it to 400).
    """
    cmd = store.get(commander_id)
    if cmd is None or not is_commander(cmd):
        raise ValueError("commander_id must be a legendary creature or planeswalker")
    ci = set(cmd.get("color_identity") or [])

    # Selected themes → (id, card-id set). themes_matched counts only these.
    selected_sets: list[tuple[str, set[str]]] = []
    for tid in theme_ids:
        th = _THEMES_BY_ID.get(tid)
        if th is not None:
            selected_sets.append((tid, _theme_card_ids(store, th)))

    pool: set[str] = set()
    for _tid, s in selected_sets:
        pool |= s

    # Free text: words that name a theme add that theme's cards to the pool;
    # remaining words narrow via oracle-text search (intersection when a theme
    # pool already exists, otherwise they seed the pool on their own).
    free_terms = [w for w in re.split(r"[\s,]+", (free_text or "").lower()) if w]
    oracle_ids: set[str] | None = None
    for w in free_terms:
        hit = next((th for th in THEMES
                    if w == th["id"] or w in th["label"].lower()), None)
        if hit is not None:
            pool |= _theme_card_ids(store, hit)
        else:
            matches = {c["id"] for c in store.oracle_search(w, limit=400)}
            oracle_ids = matches if oracle_ids is None else (oracle_ids & matches)
    if oracle_ids is not None:
        pool = (pool & oracle_ids) if pool else oracle_ids

    # Commander synergy source: EDHREC when available, else structural neighbors.
    edh = store.edhrec_for(commander_id)
    if edh:
        def syn_of(cid: str) -> float:
            return max(0.0, min(1.0, edh.get(cid, (0.0, 0.0))[0]))
    else:
        sn = dict(store.synergy_neighbors(commander_id, limit=SYN_NEIGHBOR_K))
        def syn_of(cid: str) -> float:
            return max(0.0, min(1.0, sn.get(cid, 0.0)))

    scored: list[tuple[float, str, int]] = []
    for cid in pool:
        if cid == commander_id:
            continue
        card = store.get(cid)
        if card is None:
            continue
        ier = card.get("ier")
        if ier is None:
            continue
        if card["name"] in BANLIST or "Basic" in (card.get("type_line") or ""):
            continue
        if not set(card.get("color_identity") or []) <= ci:
            continue
        matched = sum(1 for _tid, s in selected_sets if cid in s)
        themes_matched = max(matched, 1)
        relevance = 1.0 + 0.5 * (themes_matched - 1)   # 1.0, 1.5, 2.0, …
        ier_norm = min(ier / IER_NORM_CAP, 1.0)
        score = relevance * (0.5 * ier_norm + 0.5 * syn_of(cid))
        scored.append((score, cid, themes_matched))

    scored.sort(key=lambda t: (-t[0], t[1]))
    total = len(scored)
    page = scored[offset:offset + limit]
    cards = [{"card": store.get(cid), "score": round(score, 6),
              "themes_matched": tm} for score, cid, tm in page]
    return {"cards": cards, "total": total, "has_more": offset + limit < total}
