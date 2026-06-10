"""SP9 — deck synergy graph: nodes + typed weighted edges among deck cards.

SCAFFOLD — implement per docs/superpowers/plans/2026-06-10-sp6-sp11-roadmap.md §9.1.

deck_graph contract:
- nodes: one per resolvable deck card (commander included):
  {id, name, ier, category: doctor.category_of (commander gets "commander"), image}
- edges, built in ONE accumulation pass (suggest.py's trick): for each member d, walk
  cooccurrence_neighbors(d, 50) and synergy_neighbors(d, 50); keep pairs whose other end is
  also in the deck. Thresholds: lift >= 2.0 (weight = suggest.lift_to_norm(lift)),
  synergy >= 0.30 (weight = synergy).
- combo edges: for every COMPLETE spellbook combo / asserted engine within the deck, add all
  member-pairs with kind "combo", weight 1.0.
- dedupe by unordered pair with kind priority combo > synergy > cooccurrence (keep the
  highest-priority kind's edge; same kind keeps max weight).
- degree cap: sort edges weight DESC, keep an edge iff either endpoint currently has < 8
  kept edges (soft cap — an endpoint may exceed 8 via under-cap partners; bound ≤ 12 asserted
  in tests).
- return {"nodes": [...], "edges": [{a, b, kind, weight}]}; a/b are card ids with a < b.
"""

from __future__ import annotations

from .store import Store

LIFT_EDGE_MIN = 2.0
SYNERGY_EDGE_MIN = 0.30
NEIGHBOR_K = 50
DEGREE_CAP = 8


def deck_graph(store: Store, commander_id: str | None, deck_ids: list[str]) -> dict:
    """See module docstring + roadmap §9.1. Router validates via GraphResponse."""
    raise NotImplementedError("SP9 pending — roadmap §9.1")
