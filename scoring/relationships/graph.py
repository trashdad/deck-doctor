"""Resource-flow graph over card resources.

Directed edge maker -> payoff when maker.produces satisfies payoff.consumes.
candidate_pairs() yields only pairs that can have nonzero synergy (producer x
consumer per resource), avoiding the all-pairs blowup.
"""

from __future__ import annotations

from collections import defaultdict

from relationships.resources import resource_match


def _producer_consumer_index(resources: dict) -> tuple[dict, dict]:
    """resource -> set(card_ids producing it) and resource -> set(consuming it).

    Producers are indexed by their concrete resource string; consumers that ask
    for generic 'counter' are expanded so resource_match still holds via lookup.
    """
    by_prod = defaultdict(set)
    by_cons = defaultdict(set)
    for cid, r in resources.items():
        for p in r["produces"]:
            by_prod[p].add(cid)
        for c in r["consumes"]:
            by_cons[c].add(cid)
    return by_prod, by_cons


def candidate_pairs(resources: dict) -> set:
    """Unordered candidate pairs (a, b) that may have nonzero synergy."""
    by_prod, by_cons = _producer_consumer_index(resources)
    pairs: set = set()
    for cons_res, consumers in by_cons.items():
        # find producers whose product matches this consumed resource
        producers: set = set()
        for prod_res, makers in by_prod.items():
            if resource_match(prod_res, cons_res):
                producers |= makers
        for c in consumers:
            for p in producers:
                if p != c:
                    pairs.add(tuple(sorted((p, c))))
    return pairs


def neighbors_out(card_id: str, resources: dict) -> set:
    """Cards that consume something this card produces (directed maker->payoff)."""
    me = resources.get(card_id)
    if not me:
        return set()
    outs: set = set()
    for other, r in resources.items():
        if other == card_id:
            continue
        if any(resource_match(p, c) for p in me["produces"] for c in r["consumes"]):
            outs.add(other)
    return outs
