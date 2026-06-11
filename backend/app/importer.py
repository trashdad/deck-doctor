"""SP6 — text decklist importer (Moxfield / Archidekt / MTGO / MTGA formats).

parse_decklist(store, text) -> (cards, unresolved, commander_id) where
cards = [{card_id, zone, quantity}], unresolved = original lines that didn't
resolve, commander_id = the designated commander id (or None).

parse_decklist_rich(store, text) -> dict — same parsing, but returns full
structured result with Card objects resolved + fuzzy suggestions for misses.

Line shapes handled: count prefixes "1 " / "1x ", bare names, "(SET) 123" +
"*F*" + "#!Category" suffixes (stacked, stripped in a loop), "//" / "#" / "##"
comment & category lines, "SB:" lines + Sideboard/Maybeboard sections ignored,
Arena section words, "Commander: <name>" and "*CMDR*" markers. Singleton clamp:
quantity only kept for Basic lands; everything else clamps to 1; dedupe by id.
"""

from __future__ import annotations

import difflib
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


# ---------------------------------------------------------------------------
# Per-line parsing helper (shared by both public functions)
# ---------------------------------------------------------------------------

def _parse_line(raw: str) -> tuple[str, int, bool] | None:
    """Parse one raw input line into (name, qty, is_cmdr).

    Returns None for lines that should be skipped entirely (comments, blank,
    section headers, sideboard markers).
    Returns (name, qty, is_cmdr) for substantive lines — the caller still
    needs to look up the name in the store.
    """
    line = raw.strip()
    if not line or line.startswith(("//", "#", "##")):
        return None
    low = line.lower()
    if low in ("deck", "mainboard", "about", "sideboard", "maybeboard", "considering"):
        return None
    if low.startswith("sb:"):
        return None

    is_cmdr = False
    if low.startswith("commander:"):
        line = line.split(":", 1)[1].strip()
        is_cmdr = True
    if "*cmdr*" in low:
        line = re.sub(r"\*cmdr\*", "", line, flags=re.I).strip()
        is_cmdr = True

    m = _LINE.match(line)
    if not m:
        return None

    qty = int(m.group(1)) if m.group(1) else 1
    name = m.group(2)
    while True:                       # strip stacked suffixes: "(C21) 263 *F*"
        stripped = _STRIP_SUFFIX.sub("", name)
        if stripped == name:
            break
        name = stripped

    return name, qty, is_cmdr


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

        parsed = _parse_line(raw)
        if parsed is None:
            # section transition already handled above; a None here means the
            # line looked substantive but didn't match (blank / comment caught
            # above, so this path is hit only if _LINE fails to match).
            unresolved.append(raw.strip())
            continue

        name, qty, is_cmdr = parsed

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


def parse_decklist_rich(store: Store, text: str) -> dict:
    """Parse a decklist and return structured data with full Card objects and suggestions.

    Returns::

        {
          "resolved":   [{"card_id", "zone", "quantity"}],   # same rows as parse_decklist
          "unresolved": [{"line", "name", "quantity", "suggestion_ids": [id, ...]}],
          "commander_id": id | None,
        }

    For each line that fails to resolve, up to 5 fuzzy suggestions are found via
    ``difflib.get_close_matches`` and mapped through the store's name index.
    """
    if not text or not text.strip():
        return {"resolved": [], "unresolved": [], "commander_id": None}

    resolved: dict[str, dict] = {}   # card_id -> row (dedupe; sum basics)
    unresolved: list[dict] = []
    commander_id: str | None = None
    section_sideboard = False

    name_keys = list(store._name_to_id.keys())

    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue

        low = stripped.lower()
        # Section transitions (mirrored from parse_decklist)
        if low in ("deck", "mainboard", "about"):
            section_sideboard = False
            continue
        if low in ("sideboard", "maybeboard", "considering"):
            section_sideboard = True
            continue
        if low.startswith("sb:") or stripped.startswith(("//", "#", "##")):
            continue
        if section_sideboard:
            continue

        parsed = _parse_line(raw)
        if parsed is None:
            # _parse_line returns None for blank/comment lines — already handled
            # above, so this means the line was substantive but _LINE failed.
            unresolved.append({
                "line": stripped,
                "name": stripped,
                "quantity": 1,
                "suggestion_ids": _suggestions(store, stripped, name_keys),
            })
            continue

        name, qty, is_cmdr = parsed

        cid = store._name_to_id.get(name.lower())
        if cid is None:
            unresolved.append({
                "line": stripped,
                "name": name,
                "quantity": qty,
                "suggestion_ids": _suggestions(store, name, name_keys),
            })
            continue

        card = store.get(cid)
        basic = "Basic" in (card.get("type_line") or "")
        zone = "Commanders" if is_cmdr else _zone_for(card)
        row = resolved.setdefault(cid, {"card_id": cid, "zone": zone, "quantity": 0})
        if basic:
            row["quantity"] += qty
        else:
            row["quantity"] = 1
        if is_cmdr:
            row["zone"] = "Commanders"
            commander_id = cid

    # No explicit commander designation: adopt the first Legendary Creature seen.
    if commander_id is None:
        for cid, row in resolved.items():
            card = store.get(cid)
            if "Legendary Creature" in (card.get("type_line") or ""):
                commander_id = cid
                row["zone"] = "Commanders"
                break

    return {
        "resolved": list(resolved.values()),
        "unresolved": unresolved,
        "commander_id": commander_id,
    }


def _suggestions(store: Store, name: str, name_keys: list[str]) -> list[str]:
    """Return up to 5 card ids that are fuzzy-close to `name`."""
    matches = difflib.get_close_matches(
        name.lower(), name_keys, n=5, cutoff=0.6
    )
    return [store._name_to_id[m] for m in matches if m in store._name_to_id]
