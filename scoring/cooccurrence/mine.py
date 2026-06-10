"""Deterministic co-occurrence mining over decks-as-id-sets.

A pair's co-count can never exceed min(df_a, df_b), so only cards meeting the
support floor can be in a surviving pair — we restrict pair counting to those
cards, which keeps the candidate space tractable on the full corpus. All math is
plain counting; nothing here is learned or approximate.
"""

from __future__ import annotations

from collections import defaultdict
from itertools import combinations


def deck_frequencies(decks) -> dict:
    """card id -> number of decks containing it."""
    df: dict = defaultdict(int)
    for deck in decks:
        for cid in deck:
            df[cid] += 1
    return dict(df)


def mine_pairs(decks, min_support: int = 20) -> dict:
    """Return {(a,b) sorted: {co_count, lift, jaccard, support}} for pairs whose
    co-deck count >= min_support. lift = co*N / (df_a*df_b); jaccard = co/(df_a+df_b-co)."""
    n = len(decks)
    df = deck_frequencies(decks)
    eligible = {c for c, f in df.items() if f >= min_support}

    co: dict = defaultdict(int)
    for deck in decks:
        members = sorted(c for c in deck if c in eligible)
        for a, b in combinations(members, 2):
            co[(a, b)] += 1

    out: dict = {}
    for (a, b), c in co.items():
        if c < min_support:
            continue
        lift = (c * n) / (df[a] * df[b]) if df[a] and df[b] else 0.0
        jaccard = c / (df[a] + df[b] - c)
        out[(a, b)] = {"co_count": c, "lift": round(lift, 6),
                       "jaccard": round(jaccard, 6), "support": c}
    return out
