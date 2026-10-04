"""suggest_cuts ranking against a tiny fake Store (no DB)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.doctor import suggest_cuts  # noqa: E402


class _CutsStore:
    """Just the Store surface suggest_cuts reads; no co-occurrence/structural signal."""

    def __init__(self, cards: dict, edh: dict):
        self._cards, self._edh = cards, edh

    def get(self, cid):
        return self._cards.get(cid)

    def edhrec_for(self, _cmd):
        return self._edh

    def cooccurrence_neighbors(self, _cid, _k):
        return []

    def synergy_neighbors(self, _cid, _k):
        return []

    def deck_spellbook(self, _ids):
        return {"complete": [], "near": []}

    def deck_engines(self, _ids):
        return {"combos": []}


def _card(cid, name, type_line="Creature — Bear"):
    return {"id": cid, "name": name, "type_line": type_line, "mechanic_tags": []}


def test_high_inclusion_staple_outranks_low_inclusion_filler():
    cards = {
        "cmd": _card("cmd", "Commander", "Legendary Creature — Elf"),
        "staple": _card("staple", "Staple Rock", "Artifact"),
        "filler": _card("filler", "Filler Bear"),
    }
    # (synergy, inclusion): the staple has no commander-specific synergy but is in
    # 92% of this commander's decks; the filler is in 4% with no synergy either.
    edh = {"staple": (0.0, 0.92), "filler": (0.02, 0.04)}
    cuts = suggest_cuts(_CutsStore(cards, edh), "cmd", ["staple", "filler"], limit=2)
    assert [c["card_id"] for c in cuts] == ["filler", "staple"]
    assert cuts[1]["contribution"] > 0.3


def test_high_synergy_low_inclusion_card_is_still_valued():
    # A niche synergy piece (high synergy, low inclusion) must keep its value too.
    cards = {
        "cmd": _card("cmd", "Commander", "Legendary Creature — Elf"),
        "niche": _card("niche", "Niche Payoff"),
        "filler": _card("filler", "Filler Bear"),
    }
    edh = {"niche": (0.6, 0.15), "filler": (0.01, 0.05)}
    cuts = suggest_cuts(_CutsStore(cards, edh), "cmd", ["niche", "filler"], limit=2)
    assert [c["card_id"] for c in cuts] == ["filler", "niche"]
