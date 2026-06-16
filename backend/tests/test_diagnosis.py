"""Deck Doctor Diagnosis tests (vitals scorecard)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.diagnosis import VITAL_WEIGHTS, diagnose  # noqa: E402
from app.doctor import category_of  # noqa: E402
from app.store import get_store  # noqa: E402

store = get_store()
LABELS = ["Mana Curve", "Ramp", "Card Draw", "Removal", "Win Conditions"]


def _id(name: str) -> str:
    cid = store._name_to_id.get(name.lower())
    assert cid, f"card not found: {name!r}"
    return cid


def test_empty_deck_is_graceful():
    d = diagnose(store, [], None)
    assert d["score"] == 0
    assert d["verdict"] == "—"
    assert [v["label"] for v in d["vitals"]] == LABELS
    assert all(v["score"] == 0 for v in d["vitals"])


def test_sample_deck_in_range_and_five_vitals():
    ur = _id("The Ur-Dragon")
    # Pull a few ramp/card_draw cards in identity to light up some vitals.
    ramp = [cid for cid, c in store._cards.items()
            if category_of(store.get(cid)) == "ramp"][:6]
    draw = [cid for cid, c in store._cards.items()
            if category_of(store.get(cid)) == "card_draw"][:6]
    entries = [{"id": cid, "quantity": 1} for cid in {*ramp, *draw}]
    d = diagnose(store, entries, ur)

    assert 0 <= d["score"] <= 100
    assert d["verdict"] in {"CRITICAL", "UNSTABLE", "FAIR", "STABLE", "OPTIMAL"}
    assert [v["label"] for v in d["vitals"]] == LABELS
    assert len(d["vitals"]) == 5
    assert all(0 <= v["score"] <= 100 for v in d["vitals"])


def test_score_is_weighted_blend_of_vitals():
    ur = _id("The Ur-Dragon")
    ramp = [cid for cid, c in store._cards.items()
            if category_of(store.get(cid)) == "ramp"][:8]
    entries = [{"id": cid, "quantity": 1} for cid in ramp]
    d = diagnose(store, entries, ur)
    by_label = {v["label"]: v["score"] for v in d["vitals"]}
    expected = round(sum(by_label[k] * w for k, w in VITAL_WEIGHTS.items()))
    assert d["score"] == max(0, min(100, expected))
