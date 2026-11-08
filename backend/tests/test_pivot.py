"""Commander pivot finder (app.pivot) against a tiny fake Store — no DB.

Card names, ids and colour identities below are real (copied from data/cards.json);
the EDHREC (synergy, inclusion) numbers are test inputs, not real page data.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.pivot import PivotResponse, find_pivots, score_commander  # noqa: E402

# ---- real cards (id, name, color_identity, type_line) ------------------------
MEREN = ("508b1442-bf2c-4ad6-9bcf-bd894e081ab6", "Meren of Clan Nel Toth",
         ["B", "G"], "Legendary Creature — Human Shaman")
MULDROTHA = ("705b4d97-2f50-47f7-9053-d748f4337553", "Muldrotha, the Gravetide",
             ["B", "G", "U"], "Legendary Creature — Elemental Avatar")
KARADOR = ("21c718f2-b7a2-4d3d-b5de-629347e6a45b", "Karador, Ghost Chieftain",
           ["B", "G", "W"], "Legendary Creature — Centaur Spirit")
ATRAXA = ("20e44330-f880-455e-852c-16d0a985cdf0", "Atraxa, Praetors' Voice",
          ["B", "G", "U", "W"], "Legendary Creature — Phyrexian Angel Horror")
LUTRI = ("08d24f3f-bff1-4424-a029-3221c4e395b3", "Lutri, the Spellchaser",
         ["R", "U"], "Legendary Creature — Elemental Otter")  # Commander-banned
SOL_RING = ("8ae6d023-2945-47f1-bc9f-f9c5ff9f5282", "Sol Ring", [], "Artifact")
STE = ("7a8b1c49-8594-426d-b585-41140235bb0e", "Sakura-Tribe Elder", ["G"],
       "Creature — Snake Shaman")
EWIT = ("05c1ce9a-2d66-4815-aead-91257fe1ff74", "Eternal Witness", ["G"],
        "Creature — Human Shaman")
GRAVE_PACT = ("9aaced6e-f656-49d3-9130-ba255800e0a5", "Grave Pact", ["B"], "Enchantment")
COUNTERSPELL = ("9cb2478c-1672-44eb-a9a1-a103fcdf3701", "Counterspell", ["U"], "Instant")
FOREST = ("aea42376-97f6-4313-b139-7eeaf427b22b", "Forest", ["G"], "Basic Land — Forest")
SWORDS = ("68ec2aed-7662-48ae-ab25-04f74ece1e41", "Swords to Plowshares", ["W"], "Instant")

ALL = [MEREN, MULDROTHA, KARADOR, ATRAXA, LUTRI, SOL_RING, STE, EWIT, GRAVE_PACT,
       COUNTERSPELL, FOREST, SWORDS]


def _card(t):
    cid, name, ci, tl = t
    return {"id": cid, "name": name, "color_identity": ci, "type_line": tl}


class _Store:
    """Just the surface find_pivots reads: get / commanders / edhrec_for."""

    def __init__(self, edh: dict[str, dict[str, tuple[float, float]]],
                 deck_counts: dict[str, int] | None = None):
        self._cards = {t[0]: _card(t) for t in ALL}
        self._edh = edh
        self._deck_counts = deck_counts or {}

    def get(self, cid):
        c = self._cards.get(cid)
        return dict(c) if c else None

    def commanders(self, limit=0):
        out = []
        for c in self._cards.values():
            tl = c["type_line"]
            if "Legendary" in tl and ("Creature" in tl or "Planeswalker" in tl):
                d = dict(c)
                d["deck_count"] = self._deck_counts.get(c["id"], 0)
                out.append(d)
        return out

    def edhrec_for(self, cid):
        return self._edh.get(cid, {})


def _ids(*cards):
    return [c[0] for c in cards]


# Pages: Muldrotha "runs" the whole BG core; Meren runs some; Karador only Eternal
# Witness; Atraxa nothing. (synergy, inclusion) per card.
EDH = {
    MULDROTHA[0]: {STE[0]: (0.20, 0.60), EWIT[0]: (0.30, 0.70), GRAVE_PACT[0]: (0.10, 0.40),
                   SOL_RING[0]: (0.00, 0.90)},
    MEREN[0]: {STE[0]: (0.25, 0.70), EWIT[0]: (0.05, 0.50)},
    KARADOR[0]: {EWIT[0]: (0.10, 0.60)},
    ATRAXA[0]: {SOL_RING[0]: (0.00, 0.95)},
    LUTRI[0]: {COUNTERSPELL[0]: (0.30, 0.80), SOL_RING[0]: (0.0, 0.9)},
}


def test_score_commander_counts_hits_inclusion_synergy_and_off_color():
    deck = [_card(STE), _card(EWIT), _card(COUNTERSPELL)]
    m, off = score_commander(EDH[MEREN[0]], deck, set(MEREN[2]))
    assert m.hits == 2 and m.page_size == 2
    assert m.coverage == pytest.approx(2 / 3, abs=1e-4)
    assert m.inclusion_mean == pytest.approx((0.70 + 0.50) / 3, abs=1e-4)
    assert m.synergy_mean == pytest.approx((0.25 + 0.05) / 2, abs=1e-4)
    assert off == ["Counterspell"] and m.off_color_count == 1
    expected = 0.5 * (2 / 3) + 0.3 * (1.2 / 3) + 0.2 * 0.15 - 1.0 * (1 / 3)
    assert m.score == pytest.approx(expected, abs=1e-4)


def test_score_commander_no_hits_gives_none_synergy():
    m, _ = score_commander({}, [_card(STE)], {"G"})
    assert m.hits == 0 and m.synergy_mean is None and m.score == 0.0


def test_ranks_commander_whose_page_covers_the_deck_and_omits_pageless():
    store = _Store(EDH)
    deck = _ids(STE, EWIT, GRAVE_PACT, SOL_RING, FOREST)
    out = find_pivots(store, None, deck, include_all=True)
    PivotResponse(**out)  # shape is serialisable
    assert out["deck_size"] == 4            # Forest (basic) ignored
    assert out["deck_identity"] == ["B", "G"]
    names = [c["commander"]["name"] for c in out["candidates"]]
    assert names[0] == "Muldrotha, the Gravetide"
    assert names.index("Meren of Clan Nel Toth") < names.index("Karador, Ghost Chieftain")
    assert "Lutri, the Spellchaser" not in names   # banned (and off-colour anyway)
    assert out["current"] is None
    top = out["candidates"][0]
    assert top["in_identity"] is True and top["better_than_current"] is None
    assert top["metrics"].hits == 4
    assert top["reason"].startswith(
        "4 of your 4 cards appear on Muldrotha, the Gravetide's EDHREC page")
    assert {e.signal for e in top["evidence"]} == {"coverage", "edhrec_inclusion", "edhrec_synergy"}


def test_only_better_than_current_by_default():
    store = _Store(EDH)
    deck = _ids(STE, EWIT, GRAVE_PACT, SOL_RING)
    out = find_pivots(store, MEREN[0], deck)
    assert out["current"]["commander"]["name"] == "Meren of Clan Nel Toth"
    assert out["current"]["metrics"].hits == 2
    names = [c["commander"]["name"] for c in out["candidates"]]
    assert names == ["Muldrotha, the Gravetide"]
    assert out["candidates"][0]["better_than_current"] is True
    # current commander never appears as its own alternative
    assert "Meren of Clan Nel Toth" not in names
    # include_all brings the worse ones back, flagged
    out2 = find_pivots(store, MEREN[0], deck, include_all=True)
    flags = {c["commander"]["name"]: c["better_than_current"] for c in out2["candidates"]}
    assert flags["Karador, Ghost Chieftain"] is False


def test_off_color_cards_are_listed_and_capped():
    store = _Store(EDH)
    deck = _ids(STE, EWIT, COUNTERSPELL, SWORDS)
    out = find_pivots(store, None, deck, include_all=True, max_off_color=1)
    by = {c["commander"]["name"]: c for c in out["candidates"]}
    # Meren (BG) would force 2 cuts (Counterspell, Swords) > max_off_color=1 → skipped
    assert "Meren of Clan Nel Toth" not in by
    # Muldrotha (BUG) forces 1 cut (Swords) → kept, flagged, listed, penalised
    mul = by["Muldrotha, the Gravetide"]
    assert mul["in_identity"] is False and mul["off_color_names"] == ["Swords to Plowshares"]
    # identity is rendered in WUBRG order
    assert "outside UBG" in mul["reason"] and "Swords to Plowshares" in mul["reason"]
    assert any(e.signal == "off_color" and e.value == 1.0 for e in mul["evidence"])
    # Atraxa (WUBG) fits everything but her page has none of these cards → score 0
    atr = by["Atraxa, Praetors' Voice"]
    assert atr["in_identity"] is True and atr["metrics"].hits == 0
    assert atr["metrics"].score == 0.0


def test_banned_in_identity_commander_is_excluded():
    store = _Store(EDH)
    out = find_pivots(store, None, _ids(COUNTERSPELL, SOL_RING), include_all=True)
    names = [c["commander"]["name"] for c in out["candidates"]]
    assert "Lutri, the Spellchaser" not in names


def test_popularity_evidence_only_when_known():
    store = _Store(EDH, deck_counts={MULDROTHA[0]: 123})
    out = find_pivots(store, None, _ids(STE), include_all=True)
    by = {c["commander"]["name"]: c for c in out["candidates"]}
    mul_signals = {e.signal: e for e in by["Muldrotha, the Gravetide"]["evidence"]}
    assert mul_signals["popularity"].value == 123.0 and by["Muldrotha, the Gravetide"]["deck_count"] == 123
    assert "popularity" not in {e.signal for e in by["Meren of Clan Nel Toth"]["evidence"]}


def test_empty_deck_and_unknown_ids():
    store = _Store(EDH)
    out = find_pivots(store, MEREN[0], ["not-a-card", MEREN[0]])
    assert out == {"deck_size": 0, "deck_identity": [],
                   "current": {"commander": store.get(MEREN[0]), "metrics": None},
                   "candidates": []}


def test_limit_and_deterministic_tiebreak():
    store = _Store(EDH)
    out = find_pivots(store, None, _ids(STE, EWIT, GRAVE_PACT, SOL_RING),
                      include_all=True, limit=2)
    assert len(out["candidates"]) == 2
    scores = [c["metrics"].score for c in out["candidates"]]
    assert scores == sorted(scores, reverse=True)
