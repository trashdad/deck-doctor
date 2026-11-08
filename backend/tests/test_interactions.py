"""Interaction-record skeleton (app/interactions.py) + opt-in wiring in suggest.recommend.

Fixture records below are TEST FIXTURES, not real verified interactions; card ids are
resolved by name from the real store so they exist in data.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.interactions import InteractionRecord, load_jsonl, lookup  # noqa: E402
from app.store import get_store  # noqa: E402
from app.suggest import recommend  # noqa: E402

store = get_store()


def _id(name: str) -> str:
    cid = store._name_to_id.get(name.lower())
    assert cid, f"card not found: {name!r}"
    return cid


def _fixtures():
    drake, deadeye, bear = _id("Peregrine Drake"), _id("Deadeye Navigator"), _id("Grizzly Bears")
    verified = InteractionRecord(cards=(drake, deadeye), kind="combo", mechanism="etb_loop",
                                 verified_by="spellbook", confidence=1.0,
                                 receipt="FIXTURE: Deadeye Navigator blinks Peregrine Drake.")
    unverified = InteractionRecord(cards=(bear, deadeye), kind="synergy", confidence=0.9,
                                   receipt="FIXTURE: unverified sentence")
    return drake, deadeye, bear, verified, unverified


def test_lookup_requires_candidate_and_a_deck_card():
    drake, deadeye, bear, v, u = _fixtures()
    assert lookup([v, u], {deadeye}, drake) == [v]
    assert lookup([v, u], {deadeye}, bear) == [u]
    assert lookup([v, u], set(), drake) == []
    assert lookup([v, u], {drake}, drake) == []     # candidate alone is not a deck partner


def test_weight_unverified_is_discounted():
    *_, v, u = _fixtures()
    assert v.weight() == 1.0
    assert u.weight() == 0.9 * 0.5 * 0.25


def test_jsonl_roundtrip(tmp_path):
    drake, deadeye, *_ = _fixtures()
    p = tmp_path / "ix.jsonl"
    p.write_text(json.dumps({"cards": [drake, deadeye], "kind": "combo",
                             "verified_by": "none", "confidence": 0.5}) + "\n")
    recs = load_jsonl(p)
    assert len(recs) == 1 and not recs[0].verified
    assert load_jsonl(None) == [] and load_jsonl(tmp_path / "missing") == []


def test_recommend_default_unchanged_and_receipt_only_when_verified():
    drake, deadeye, bear, v, u = _fixtures()
    cmd = _id("Talrand, Sky Summoner")
    base = recommend(store, cmd, [deadeye], limit=50, explain=True)
    on = recommend(store, cmd, [deadeye], limit=50, explain=True,
                   interactions=[v, u], interaction_weight=1.0)
    # weight 0 -> scores and ranking untouched (receipts may still be attached as
    # reasons: _reasons lists verified interactions independently of the weight).
    zero = recommend(store, cmd, [deadeye], limit=50, explain=True, interactions=[v, u])
    key = lambda out: [(s["card"]["id"], s["score"]) for s in out["suggestions"]]  # noqa: E731
    assert key(zero) == key(base)
    assert {k: v_ for k, v_ in zero.items() if k != "suggestions"} == \
           {k: v_ for k, v_ in base.items() if k != "suggestions"}
    by_id = {s["card"]["id"]: s for s in on["suggestions"]}
    assert drake in by_id
    sigs = [r for r in by_id[drake]["reasons"] if r["signal"] == "interaction"]
    assert sigs and sigs[0]["detail"].startswith("FIXTURE: Deadeye")
    if bear in by_id:
        assert not [r for r in by_id[bear]["reasons"] if r["signal"] == "interaction"]
