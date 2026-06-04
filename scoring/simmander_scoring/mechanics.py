"""Mechanic tagging for MTG cards.

Translates a card's oracle text / type line / keywords into a set of behavioral
tags. This is the substrate for the Combinatorial Synergy Score (CSS): we score
synergy by how a card's *producer* tags line up with another card's *payoff*
tags (e.g. "creates tokens" <-> "whenever a token enters"), plus shared
"parasitic" mechanic clusters that the Lift model flags (infect, energy, mutate).

Pure-Python and dependency-free so it runs anywhere. The regex taxonomy is the
documented seam where simmander's machine-coded mechanic tags will plug in
(see docs/asset-inventory.md) — once that DB is reachable we prefer its tags and
fall back to this text scan only for cards it doesn't cover.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

# Each tag maps to a list of case-insensitive regex patterns matched against the
# lowercased oracle text. Tags are grouped so CSS can reward complementary pairs.
_TAG_PATTERNS: dict[str, list[str]] = {
    # --- token sub-engine ---
    "token_producer": [r"create[s]? .*token", r"creates? twice that many"],
    "token_payoff": [
        r"if .*tokens? would be created",
        r"whenever .*token .*enters",
        r"for each .*token",
    ],
    # --- +1/+1 counter sub-engine ---
    "counter_producer": [
        r"\+1/\+1 counter",
        r"proliferate",
        r"put .*counters? on",
    ],
    "counter_payoff": [
        r"if .*counters? would be put",
        r"twice that many of those counters",
        r"that many plus one",
        r"for each .*counter",
    ],
    # --- sacrifice / aristocrats ---
    "sacrifice_outlet": [r"sacrifice (a|an|target|x|that)"],
    "sacrifice_payoff": [r"whenever .*dies", r"whenever .*you sacrifice"],
    # --- card advantage / ramp / interaction (mostly for IER + filters) ---
    "card_draw": [r"draw (a|two|three|x|that many|cards?)", r"you may draw a card"],
    "ramp": [r"add \{[wubrgc0-9]", r"search your library for .*land"],
    "removal": [r"destroy target", r"exile target creature", r"target creature gets -"],
    "board_wipe": [r"destroy all", r"each creature", r"all creatures get -"],
    "lifegain": [r"gain .* life", r"gains life"],
    "landfall": [r"landfall", r"whenever a land enters"],
}

# Parasitic / closed-loop mechanics: cards sharing one of these are uniquely bound
# to each other (high Lift). These are flagged from keywords and oracle text.
PARASITIC_MECHANICS: tuple[str, ...] = (
    "infect",
    "energy",
    "mutate",
    "poison",
    "toxic",
)

# Complementary (producer -> payoff) pairs that drive exponential synergy.
COMPLEMENTARY_PAIRS: tuple[tuple[str, str], ...] = (
    ("token_producer", "token_payoff"),
    ("counter_producer", "counter_payoff"),
    ("sacrifice_outlet", "sacrifice_payoff"),
    ("landfall", "counter_producer"),  # landfall proliferate engines
)

_COMPILED = {
    tag: [re.compile(p, re.IGNORECASE) for p in pats]
    for tag, pats in _TAG_PATTERNS.items()
}


@dataclass
class CardTags:
    """Behavioral fingerprint of a card."""

    mechanic_tags: set[str] = field(default_factory=set)
    parasitic: set[str] = field(default_factory=set)

    def as_sorted(self) -> list[str]:
        return sorted(self.mechanic_tags | {f"parasitic:{p}" for p in self.parasitic})


def tag_card(card: dict) -> CardTags:
    """Derive behavioral tags from a Scryfall-format card dict.

    Tolerant of missing keys (Doc A: "handle missing JSON keys gracefully").
    """
    oracle = (card.get("oracle_text") or "").lower()
    type_line = (card.get("type_line") or "").lower()
    keywords = [k.lower() for k in (card.get("keywords") or [])]
    haystack = f"{oracle}\n{type_line}\n{' '.join(keywords)}"

    tags: set[str] = set()
    for tag, patterns in _COMPILED.items():
        if any(p.search(haystack) for p in patterns):
            tags.add(tag)

    parasitic = {m for m in PARASITIC_MECHANICS if m in haystack}

    return CardTags(mechanic_tags=tags, parasitic=parasitic)


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)
