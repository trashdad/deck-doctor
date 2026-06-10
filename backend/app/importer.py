"""SP6 — text decklist importer (Moxfield / Archidekt / MTGO / MTGA formats).

SCAFFOLD — implement per docs/superpowers/plans/2026-06-10-sp6-sp11-roadmap.md §6.3.
The roadmap contains the EXACT regexes and algorithm — implement as written, including:
- count prefixes `1 ` / `1x `, bare names, `(SET) 123` + `*F*` + `#!Category` suffix stripping
  (stacked suffixes stripped in a loop), `//` and `##` comment/category lines,
  `SB:` lines and Sideboard/Maybeboard sections ignored, Arena section words
  (Deck/Mainboard/About reset; Sideboard/Maybeboard/Considering enter sideboard mode),
  `Commander: <name>` and `*CMDR*` markers set the commander,
- name resolution via store._name_to_id (lowercased; `A // B` front faces already indexed),
- singleton clamp: quantity kept only for cards whose type_line contains "Basic",
- dedupe by card_id (basics sum quantities, others stay 1),
- returns (cards, unresolved, commander_id) where cards rows are
  {"card_id": str, "zone": str, "quantity": int} and unresolved are the ORIGINAL lines.

Zone assignment: `_zone_for(card)` maps doctor.category_of(card) to frontend zone names:
  land→"Lands", ramp→"Ramp", card_draw→"Card Draw", removal→"Removal",
  board_wipe→"Board Wipes", counters→"Counters", tokens→"Tokens", synergy→"Utility";
the designated commander (Legendary Creature) goes to "Commanders".
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
    """Parse a pasted decklist. See module docstring + roadmap §6.3 for the contract."""
    raise NotImplementedError("SP6 pending — roadmap §6.3")
