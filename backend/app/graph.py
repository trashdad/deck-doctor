"""SP9 — deck synergy graph: nodes + typed weighted edges among deck cards.

Edges are built among deck cards only, in one accumulation pass over each member's
indexed neighbor lists (suggest.py's trick), plus combo edges for every complete
spellbook combo / asserted engine in the deck. Deduped per unordered pair with kind
priority combo > synergy > cooccurrence, then a soft per-node degree cap.
"""

from __future__ import annotations

from collections import defaultdict

from .doctor import category_of
from .store import Store
from .suggest import lift_to_norm

LIFT_EDGE_MIN = 2.0
SYNERGY_EDGE_MIN = 0.30
NEIGHBOR_K = 50
DEGREE_CAP = 8
_KIND_PRIORITY = {"combo": 3, "synergy": 2, "cooccurrence": 1}


def deck_graph(store: Store, commander_id: str | None, deck_ids: list[str]) -> dict:
    nodeset = set(deck_ids)
    if commander_id:
        nodeset.add(commander_id)

    nodes: list[dict] = []
    valid: set[str] = set()
    for cid in nodeset:
        card = store.get(cid)
        if card is None:
            continue
        valid.add(cid)
        cat = "commander" if cid == commander_id else category_of(card)
        img = (card.get("image_uris") or {}).get("normal")
        nodes.append({"id": cid, "name": card["name"], "ier": card.get("ier"),
                      "category": cat, "image": img})

    # edges_map[(a, b)] = (priority, kind, weight) with a < b
    edges_map: dict[tuple[str, str], tuple[int, str, float]] = {}

    def consider(x: str, y: str, kind: str, weight: float) -> None:
        if x == y or x not in valid or y not in valid:
            return
        a, b = (x, y) if x < y else (y, x)
        pr = _KIND_PRIORITY[kind]
        cur = edges_map.get((a, b))
        if cur is None or pr > cur[0] or (pr == cur[0] and weight > cur[2]):
            edges_map[(a, b)] = (pr, kind, weight)

    for d in valid:
        for other, lift, _jac in store.cooccurrence_neighbors(d, NEIGHBOR_K):
            if other in valid and lift >= LIFT_EDGE_MIN:
                consider(d, other, "cooccurrence", lift_to_norm(lift))
        for other, synergy in store.synergy_neighbors(d, NEIGHBOR_K):
            if other in valid and synergy >= SYNERGY_EDGE_MIN:
                consider(d, other, "synergy", synergy)

    # Combo edges: every pair within a complete spellbook combo / asserted engine.
    groups: list[list[str]] = []
    sb = store.deck_spellbook(list(valid))
    groups += [c["members"] for c in sb["complete"]]
    eng = store.deck_engines(list(valid))
    groups += [e["members"] for e in eng["combos"]]
    for members in groups:
        ms = [m for m in members if m in valid]
        for i in range(len(ms)):
            for j in range(i + 1, len(ms)):
                consider(ms[i], ms[j], "combo", 1.0)

    # Flatten, then degree-cap (sort by weight desc; keep while either end under cap).
    all_edges = [{"a": a, "b": b, "kind": k, "weight": round(w, 4)}
                 for (a, b), (_pr, k, w) in edges_map.items()]
    all_edges.sort(key=lambda e: -e["weight"])
    degree: dict[str, int] = defaultdict(int)
    kept: list[dict] = []
    for e in all_edges:
        if degree[e["a"]] < DEGREE_CAP or degree[e["b"]] < DEGREE_CAP:
            kept.append(e)
            degree[e["a"]] += 1
            degree[e["b"]] += 1
    return {"nodes": nodes, "edges": kept}
