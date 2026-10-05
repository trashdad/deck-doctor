"""suggest_cuts ranking against a tiny fake Store (no DB)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.doctor import suggest_cuts  # noqa: E402


class _CutsStore:
    """Just the Store surface suggest_cuts reads; no co-occurrence/structural signal."""

    def __init__(self, cards: dict, edh: dict, staple: dict | None = None):
        self._cards, self._edh, self._staple = cards, edh, staple or {}

    def staple_score(self, cid):
        return self._staple.get(cid, 0.0)

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


def test_staple_protected_without_any_edhrec_data():
    """Review #2: staple protection must not depend on EDHREC. With edh={} (commander
    has no EDHREC page) Sol Ring used to tie the filler at 0 and could be cut first."""
    cards = {
        "cmd": _card("cmd", "Obscure Commander", "Legendary Creature — Elf"),
        "staple": _card("staple", "Sol Ring", "Artifact"),
        "filler": _card("filler", "Filler Bear"),
    }
    staple = {"staple": 0.97, "filler": 0.01}       # corpus deck-frequency, 0..1
    cuts = suggest_cuts(_CutsStore(cards, {}, staple), "cmd", ["staple", "filler"], limit=2)
    assert [c["card_id"] for c in cuts] == ["filler", "staple"]
    assert cuts[1]["contribution"] > 0.3


def test_edhrec_reason_shows_raw_negative_synergy():
    """Review #7: synergy is clamped to [0,1] for SCORING, but the explanation must show
    the real EDHREC value — a negative synergy was displayed as +0.00."""
    cards = {
        "cmd": _card("cmd", "Commander", "Legendary Creature — Elf"),
        "x": _card("x", "Off-plan Card"),
    }
    cuts = suggest_cuts(_CutsStore(cards, {"x": (-0.15, 0.50)}), "cmd", ["x"], limit=1)
    edh_reason = next(r for r in cuts[0]["reasons"] if r["signal"] == "edhrec")
    assert "-0.15" in edh_reason["detail"]
    assert "50%" in edh_reason["detail"]
