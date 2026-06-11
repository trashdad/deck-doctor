"""SP12 — Fill-in-my-lands manabase optimizer.

fill_lands(store, commander_id, deck_ids, template, max_price) -> list[dict]

Each returned dict: {"card_id", "zone": "Lands", "quantity", "reason"}.
The function is fill-only: it counts current land cards in deck_ids and only
adds enough to reach the template's land quota.  Dual lands are included as
long as they are within color identity and under the price cap.

Nonbasic/basic split rule:
  - Deficit = template_land - current_land_count.
  - nonbasic_cap = deficit - max(0, min(8, deficit // 3))
    (leaves at least ~8 basic slots in multicolor decks so manabase
    is never all-nonbasic; in practice: deficit=20 -> cap=16, deficit=10 -> cap=7)
  - Remaining slots filled by pip-ratio basics (shared logic with doctor._add_lands).
"""

from __future__ import annotations

from collections import Counter

from .doctor import (
    BASIC_FOR_COLOR,
    BANLIST,
    _WUBRG,
    _PIP,
    _emit_basic,
    category_of,
)
from .store import Store

DEFAULT_LAND_TARGET = 37


def _pip_basics(store: Store, ci: set[str], present: set[str],
                added: list[dict], basic_slots: int) -> None:
    """Fill `basic_slots` with basics proportional to pip distribution of nonland cards.

    Extracted from doctor._add_lands part (b) so both share identical logic.
    """
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
    fracs.sort(key=lambda t: (-t[0], _WUBRG.index(t[1])))
    for i in range(remainder):
        floors[fracs[i % len(fracs)][1]] = floors.get(fracs[i % len(fracs)][1], 0) + 1
    for c in _WUBRG:
        n = floors.get(c, 0)
        if n:
            _emit_basic(store, added, BASIC_FOR_COLOR[c], n)


def _land_allowed_by_ci(produced_mana: list[str], ci: set[str]) -> bool:
    """True if a land's produced mana is compatible with the commander's CI.

    A land is allowed if every *colored* mana symbol it produces is within CI.
    Colorless (C) or empty produced_mana (utility/colorless lands) are always allowed.
    """
    for sym in produced_mana:
        if sym in _WUBRG and sym not in ci:
            return False
    return True


def fill_lands(
    store: Store,
    commander_id: str,
    deck_ids: list[str],
    template: dict,
    max_price: float = 0.0,
) -> list[dict]:
    """Fill the deck's manabase to the template's land quota.

    Returns a list of add-dicts: {"card_id", "zone", "quantity", "reason"}.
    Returns [] if the deck already meets or exceeds the land quota.

    Args:
        store:        The loaded Store instance.
        commander_id: Scryfall id of the commander (excluded from deck_ids count).
        deck_ids:     The current deck cards (excluding commander).
        template:     Dict with at least a "land" key for the quota.
        max_price:    0 or negative = no price cap; positive = skip lands with
                      usd > max_price (null-priced lands always pass).
    """
    target_land = template.get("land", DEFAULT_LAND_TARGET)

    # Count current lands (exclude commander)
    current_land_count = sum(
        1 for cid in deck_ids
        if cid != commander_id and store.get(cid) is not None
        and category_of(store.get(cid)) == "land"  # type: ignore[arg-type]
    )
    deficit = max(target_land - current_land_count, 0)
    if deficit <= 0:
        return []

    ci: set[str] = set((store.get(commander_id) or {}).get("color_identity") or [])
    present: set[str] = set(deck_ids) | {commander_id}
    added: list[dict] = []

    # Nonbasic cap: leave room for at least some basics.
    # Rule: nonbasics <= deficit - max(0, min(8, deficit // 3))
    # Examples: deficit=37 -> cap=32, deficit=20 -> cap=16, deficit=10 -> cap=7, deficit=3 -> cap=3
    basic_reserve = max(0, min(8, deficit // 3))
    nonbasic_cap = deficit - basic_reserve

    # (a) Nonbasic land staples in color identity, under price cap.
    nonbasic_added = 0
    for cid, _freq in store.staples_for_colors(ci, limit=800, exclude=present):
        if nonbasic_added >= nonbasic_cap:
            break
        card = store.get(cid)
        if card is None:
            continue
        if "Land" not in (card.get("type_line") or ""):
            continue
        if card["name"] in BANLIST:
            continue

        # CI check via land_meta.produced_mana (authoritative); fallback: allow it
        meta = store.land_meta.get(cid)
        if meta is not None:
            produced = meta.get("produced_mana") or []
            if not _land_allowed_by_ci(produced, ci):
                continue
            # Price cap
            if max_price > 0:
                usd = meta.get("usd")
                if usd is not None and usd > max_price:
                    continue
        # If not in land_meta: staples_for_colors already checked color_identity,
        # so allow it (conservative — won't exclude a valid land due to missing data).

        added.append({
            "card_id": cid,
            "zone": "Lands",
            "quantity": 1,
            "reason": "land staple" if meta is None else (
                f"land staple (${meta['usd']:.2f})" if meta.get("usd") is not None
                else "land staple"
            ),
        })
        present.add(cid)
        nonbasic_added += 1

    # (b) Basics for remaining slots, by pip ratio.
    basic_slots = deficit - nonbasic_added
    _pip_basics(store, ci, present, added, basic_slots)

    return added
