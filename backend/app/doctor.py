"""SP8 — Deck Doctor: type-aware deck completion + cut suggestions.

SCAFFOLD — implement per docs/superpowers/plans/2026-06-10-sp6-sp11-roadmap.md §8.
`category_of` below is FINAL (shared with SP6 import zoning and SP9 graph nodes).

complete_deck (roadmap §8.2, deterministic greedy):
- nonland loop: pool = suggest.recommend(limit=120); pick argmax of
  score * (1.5 if the card's category has a deficit vs TEMPLATE else 1.0);
  refresh the pool every RESCORE_EVERY adds; staple-fill when the pool runs dry;
  stop at 62 nonlands (100 - commander - TEMPLATE["land"]).
- lands: top NONBASIC_LAND_CAP land staples in CI, then basics by colored-pip ratio of the
  final nonland list (regex r"\\{([WUBRG])(?:/[WUBRGP])?\\}" on mana_cost; first color of
  hybrids; remainder by largest fractional part, WUBRG tie order; colorless CI → Wastes).
  Basics emit ONE row each with quantity=N.
- every selection tiebreaks (-score, card_id); zero randomness.

suggest_cuts (roadmap §8.3):
- contribution(c) = SP5 blend of c against the REST of the deck, computed with ONE
  accumulation pass over all members' neighbor lists (when a neighbor is also in-deck,
  credit BOTH endpoints), then /(n-1).
- engine term: 1.0 iff c belongs to any COMPLETE spellbook combo / asserted engine in deck.
- never cut: commander, lands, members of complete combos. Worst (lowest) first.
"""

from __future__ import annotations

from .store import Store

CATEGORIES = ("commander", "land", "ramp", "card_draw", "removal",
              "board_wipe", "counters", "tokens", "synergy")

TEMPLATE = {
    "land": 37, "ramp": 10, "card_draw": 10, "removal": 9, "board_wipe": 3,
}
NONBASIC_LAND_CAP = 12
RESCORE_EVERY = 10

BASIC_FOR_COLOR = {"W": "Plains", "U": "Island", "B": "Swamp",
                   "R": "Mountain", "G": "Forest"}


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


def complete_deck(store: Store, commander_id: str, deck_ids: list[str],
                  template: dict = TEMPLATE) -> dict:
    """-> {"added": [{card_id, zone, quantity, reason}], "final_size": int}.

    See module docstring + roadmap §8.2. The /deck/complete router resolves card_id→Card.
    """
    raise NotImplementedError("SP8 pending — roadmap §8.2")


def suggest_cuts(store: Store, commander_id: str, deck_ids: list[str],
                 limit: int = 10) -> list[dict]:
    """-> [{card_id, contribution, reasons: [{signal, detail, value}]}] worst-first.

    See module docstring + roadmap §8.3.
    """
    raise NotImplementedError("SP8 pending — roadmap §8.3")
