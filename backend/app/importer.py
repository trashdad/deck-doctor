"""SP6 — text decklist importer (Moxfield / Archidekt / MTGO / MTGA formats).

parse_decklist(store, text) -> (cards, unresolved, commander_id) where
cards = [{card_id, zone, quantity}], unresolved = original lines that didn't
resolve, commander_id = the designated commander id (or None).

Line shapes handled: count prefixes "1 " / "1x ", bare names, "(SET) 123" +
"*F*" + "#!Category" suffixes (stacked, stripped in a loop), "//" / "#" / "##"
comment & category lines, "SB:" lines + Sideboard/Maybeboard sections ignored,
Arena section words, "Commander: <name>" and "*CMDR*" markers. Singleton clamp:
quantity only kept for Basic lands; everything else clamps to 1; dedupe by id.
"""

from __future__ import annotations

import re

from .store import Store

_LINE = re.compile(r"^\s*(?:(\d+)\s*[xX]?\s+)?(.+?)\s*$")
_STRIP_SUFFIX = re.compile(r"\s*(\((\w{2,6})\)\s*[\w-]*|\*[A-Za-z]+\*|#!?[\w\s-]+|\[\w+\])\s*$")

_CATEGORY_TO_ZONE = {
    "land": "Lands", "ramp": "Ramp", "card_draw": "Card Draw", "removal": "Removal",
    "board_wipe": "Board Wipes", "counters": "Counters", "tokens": "Tokens",
    "synergy": "Utility",
}


def _zone_for(card: dict) -> str:
    from .doctor import category_of
    return _CATEGORY_TO_ZONE.get(category_of(card), "Utility")


def parse_decklist(store: Store, text: str) -> tuple[list[dict], list[str], str | None]:
    cards: dict[str, dict] = {}          # card_id -> row (dedupe; sum basics)
    unresolved: list[str] = []
    commander_id: str | None = None
    section_sideboard = False

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("//", "#", "##")):
            continue
        low = line.lower()
        if low in ("deck", "mainboard", "about"):
            section_sideboard = False
            continue
        if low in ("sideboard", "maybeboard", "considering"):
            section_sideboard = True
            continue
        if low.startswith("sb:"):
            continue
        if section_sideboard:
            continue

        is_cmdr = False
        if low.startswith("commander:"):
            line = line.split(":", 1)[1].strip()
            is_cmdr = True
        if "*cmdr*" in low:
            line = re.sub(r"\*cmdr\*", "", line, flags=re.I).strip()
            is_cmdr = True

        m = _LINE.match(line)
        if not m:
            unresolved.append(raw.strip())
            continue
        qty = int(m.group(1)) if m.group(1) else 1
        name = m.group(2)
        while True:                       # strip stacked suffixes: "(C21) 263 *F*"
            stripped = _STRIP_SUFFIX.sub("", name)
            if stripped == name:
                break
            name = stripped

        cid = store._name_to_id.get(name.lower())
        if cid is None:
            unresolved.append(raw.strip())
            continue

        card = store.get(cid)
        basic = "Basic" in (card.get("type_line") or "")
        zone = "Commanders" if is_cmdr else _zone_for(card)
        row = cards.setdefault(cid, {"card_id": cid, "zone": zone, "quantity": 0})
        if basic:
            row["quantity"] += qty
        else:
            row["quantity"] = 1
        if is_cmdr:
            row["zone"] = "Commanders"
            commander_id = cid

    # No explicit commander designation: adopt the first Legendary Creature seen.
    if commander_id is None:
        for cid, row in cards.items():
            card = store.get(cid)
            if "Legendary Creature" in (card.get("type_line") or ""):
                commander_id = cid
                row["zone"] = "Commanders"
                break

    return list(cards.values()), unresolved, commander_id
