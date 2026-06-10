"""EDHREC commander->card metrics -> directional synergy in [0, 1].

EDHREC's published synergy is roughly [-1, +1+]. For fusion we use it as a
one-directional BOOST (commander a -> card b), so we clamp to [0, 1]: negative
"anti-synergy" is SP1's separate axis, not a co-occurrence boost. Directional by
construction — only the (commander, card) key is emitted, never the reverse.
"""

from __future__ import annotations


def directional_synergy(rows) -> dict:
    """rows = [(commander_id, card_id, synergy)] -> {(commander_id, card_id): [0,1]}.

    On duplicate (commander, card) keeps the max synergy.
    """
    out: dict = {}
    for commander_id, card_id, synergy in rows:
        val = max(0.0, min(1.0, float(synergy)))
        key = (commander_id, card_id)
        if val > out.get(key, -1.0):
            out[key] = round(val, 6)
    return out
