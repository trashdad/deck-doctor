"""Multi-card engine mining + combo-candidate flagging over the resource graph.

Engine = connected member set (k in [2..5]) chained by producer->consumer resource
flow. Combo candidate = engine whose directed flow contains a cycle (potential
unbounded loop) — flagged for review, NEVER asserted as a real infinite combo.

Scalability design
------------------
The naive approach scans ALL resources for each extension step, giving O(seeds *
kmax * |resources|) = ~10^11 ops on 30k-card corpus.  Instead we build an
undirected adjacency map ONCE from candidate_pairs(), giving O(pairs) pre-work
and O(deg) per extension step — tractable even with 3.5M candidate pairs because
the actual adjacency list per card is bounded by how many distinct resource
relationships a card participates in.

mine_engines signature deviates from the plan's code body by:
  - Building adj[cid] = set of neighbor ids ONCE from candidate_pairs()
  - Extending member sets via adj[member] lookups, NOT by scanning all resources
  - Accepting seeds (override) and max_seeds (truncation with stderr notice)
"""

from __future__ import annotations

import sys

from relationships.resources import resource_match


def _feeds(a: str, b: str, res: dict) -> bool:
    """True if a produces a resource that b consumes."""
    ra = res.get(a)
    rb = res.get(b)
    if not ra or not rb:
        return False
    return any(resource_match(p, c) for p in ra["produces"] for c in rb["consumes"])


def _connects(card: str, members: list, res: dict) -> bool:
    """card extends the set if it feeds, or is fed by, any current member."""
    return any(_feeds(card, m, res) or _feeds(m, card, res) for m in members)


def has_cycle(members: list, res: dict) -> bool:
    """Directed cycle among members using producer->consumer edges (DFS)."""
    nodes = list(members)
    adj = {n: [m for m in nodes if m != n and _feeds(n, m, res)] for n in nodes}
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in nodes}

    def dfs(u: str) -> bool:
        color[u] = GRAY
        for v in adj[u]:
            if color[v] == GRAY:
                return True
            if color[v] == WHITE and dfs(v):
                return True
        color[u] = BLACK
        return False

    return any(color[n] == WHITE and dfs(n) for n in nodes)


def mine_engines(
    resources: dict,
    kmax: int = 5,
    max_per_seed: int = 50,
    seeds=None,
    max_seeds: int | None = None,
) -> list[dict]:
    """Greedy engine mining from producer->consumer seed pairs.

    Scalable version: builds an adjacency map once from candidate_pairs() and
    extends member sets via adj[member] lookups instead of scanning all resources.

    Parameters
    ----------
    resources   : {card_id: {"produces": set, "consumes": set}}
    kmax        : maximum engine size (cards)
    max_per_seed: frontier cap per seed pair (prevents fan-out explosion)
    seeds       : override seed list; if None uses sorted(candidate_pairs(resources))
    max_seeds   : if set, use only the first max_seeds seeds; prints a notice to
                  stderr when truncating so the caller knows it's a partial run.
    """
    from relationships.graph import candidate_pairs

    if seeds is None:
        all_seeds = sorted(candidate_pairs(resources))
    else:
        all_seeds = list(seeds)

    total = len(all_seeds)
    if max_seeds is not None and total > max_seeds:
        used_seeds = all_seeds[:max_seeds]
        print(
            f"mine_engines: using {max_seeds}/{total} seeds (truncated)",
            file=sys.stderr,
        )
    else:
        used_seeds = all_seeds

    # Build undirected adjacency map ONCE: adj[cid] = set of neighbors in candidate pairs.
    # This is O(pairs) and lets us skip the O(|resources|) scan during extension.
    adj: dict[str, set] = {}
    for a, b in all_seeds:  # use full set so adj is correct even with seed truncation
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)

    seen: set = set()
    engines: list[dict] = []

    for a, b in used_seeds:
        frontier = [[a, b]]
        grown = 0
        while frontier and grown < max_per_seed:
            members = frontier.pop()
            key = frozenset(members)
            if key in seen:
                continue   # already processed; don't re-expand duplicates
            seen.add(key)
            cycle = has_cycle(members, resources)
            engines.append({
                "members": sorted(members),
                "kind": "cycle" if cycle else "chain",
                "candidate": cycle,
            })
            grown += 1
            if len(members) >= kmax:
                continue
            # Gather neighbor candidates from adjacency (not all resources)
            neighbor_cands: set = set()
            for m in members:
                neighbor_cands |= adj.get(m, set())
            neighbor_cands -= set(members)

            for cand in sorted(neighbor_cands):
                # Verify actual resource connectivity before extending
                if _connects(cand, members, resources):
                    new = sorted(members + [cand])
                    if frozenset(new) not in seen:
                        frontier.append(new)
    return engines


def deck_engines(resources: dict, deck_ids: list, kmax: int = 5) -> list[dict]:
    """Engines wholly contained in a given deck (online, deck <= ~100 cards)."""
    sub = {cid: resources[cid] for cid in deck_ids if cid in resources}
    return mine_engines(sub, kmax=kmax)
