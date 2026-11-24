"""Interaction-record skeleton (app/interactions.py) + opt-in wiring in suggest.recommend.

Fixture records below are TEST FIXTURES, not real verified interactions; card ids are
resolved by name from the real store so they exist in data.
"""
import json
import sys
from pathlib import Path

import pytest

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


def test_unverified_record_scores_but_never_states_its_receipt():
    """The old check sat inside `if bear in by_id` and was vacuous whenever Grizzly
    Bears missed the top 50. Use a candidate that IS listed, prove the unverified
    record matched (score moved), and that its receipt is not shown."""
    drake, deadeye, *_ = _fixtures()
    cmd = _id("Talrand, Sky Summoner")
    base = recommend(store, cmd, [deadeye], limit=50, explain=True)
    cand = next(s for s in base["suggestions"] if s["card"]["id"] != drake)
    cid = cand["card"]["id"]
    rec = InteractionRecord(cards=(cid, deadeye), kind="synergy", confidence=0.9,
                            receipt="FIXTURE: unverified sentence")
    assert not rec.verified
    on = recommend(store, cmd, [deadeye], limit=50, explain=True,
                   interactions=[rec], interaction_weight=1.0)
    by_id = {s["card"]["id"]: s for s in on["suggestions"]}
    assert cid in by_id
    assert by_id[cid]["score"] > cand["score"]                    # the record was used
    assert not [r for r in by_id[cid]["reasons"] if r["signal"] == "interaction"]


def test_lookup_k3_record_needs_all_other_pieces_in_deck():
    """Plan §3: a k>=3 record contributes only when >= k-1 pieces are in the deck."""
    rec = InteractionRecord(cards=("a", "b", "c"), kind="combo", verified_by="engine",
                            confidence=1.0)
    assert lookup([rec], {"a"}, "c") == []
    assert lookup([rec], {"a", "b"}, "c") == [rec]
    assert lookup([rec], {"a", "b", "c"}, "c") == [rec]
    pair = InteractionRecord(cards=("a", "c"), kind="synergy", confidence=0.5)
    assert lookup([pair], {"a"}, "c") == [pair]


def test_load_jsonl_skips_bad_lines_and_keeps_good_ones(tmp_path):
    good = {"cards": ["a", "b"], "kind": "combo", "verified_by": "spellbook",
            "confidence": 1.0}
    lines = [json.dumps(good), "{not json", json.dumps({**good, "kind": "nope"}),
             json.dumps({**good, "cards": ["a"]}), json.dumps({**good, "confidence": 2}),
             json.dumps({"kind": "combo"}), json.dumps([1, 2]),
             json.dumps({**good, "cards": ["c", "d"]})]
    p = tmp_path / "ix.jsonl"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    recs = load_jsonl(p)
    assert [r.cards for r in recs] == [("a", "b"), ("c", "d")]


def _top_candidate(cmd, deck):
    base = recommend(store, cmd, deck, limit=10)
    top = base["suggestions"][0]
    return base, top["card"]["id"], top["score"]


def test_anti_synergy_reduces_score_when_weight_on():
    """An anti-synergy record (KIND_WEIGHT -0.7) must LOWER the candidate's score; it was
    discarded by max(0.0, w) so negative signals had no effect (bug 2026-11-24)."""
    _, deadeye, *_ = _fixtures()
    cmd = _id("Talrand, Sky Summoner")
    _, cand, base_score = _top_candidate(cmd, [deadeye])
    anti = InteractionRecord(cards=(cand, deadeye), kind="anti-synergy",
                             verified_by="engine", confidence=1.0)
    w = 0.01   # small enough that the candidate stays positive (and listed)
    on = recommend(store, cmd, [deadeye], limit=50, interactions=[anti],
                   interaction_weight=w)
    by_id = {s["card"]["id"]: s["score"] for s in on["suggestions"]}
    assert cand in by_id
    assert by_id[cand] == pytest.approx(base_score - w * 0.7, abs=2e-6)


def test_anti_synergy_flag_off_is_unchanged():
    _, deadeye, *_ = _fixtures()
    cmd = _id("Talrand, Sky Summoner")
    base, cand, _ = _top_candidate(cmd, [deadeye])
    anti = InteractionRecord(cards=(cand, deadeye), kind="anti-synergy",
                             verified_by="engine", confidence=1.0)
    off = recommend(store, cmd, [deadeye], limit=10, interactions=[anti])  # default weight 0
    key = lambda out: [(s["card"]["id"], s["score"]) for s in out["suggestions"]]  # noqa: E731
    assert key(off) == key(base)


def test_per_member_takes_max_signed_weight():
    """Plan §3: per deck member, max(confidence x kind_weight) over its records — a member
    with both a synergy and an anti-synergy record counts the synergy; one with only an
    anti-synergy record counts negative."""
    _, deadeye, bear, *_ = _fixtures()
    cmd = _id("Talrand, Sky Summoner")
    deck = [deadeye, bear]
    _, cand, base_score = _top_candidate(cmd, deck)
    syn = InteractionRecord(cards=(cand, deadeye), kind="synergy",
                            verified_by="engine", confidence=1.0)          # +0.5
    anti_d = InteractionRecord(cards=(cand, deadeye), kind="anti-synergy",
                               verified_by="engine", confidence=1.0)       # -0.7 (masked)
    anti_b = InteractionRecord(cards=(cand, bear), kind="anti-synergy",
                               verified_by="engine", confidence=0.5)       # -0.35
    w = 0.01
    on = recommend(store, cmd, deck, limit=50, interactions=[syn, anti_d, anti_b],
                   interaction_weight=w)
    by_id = {s["card"]["id"]: s["score"] for s in on["suggestions"]}
    assert by_id[cand] == pytest.approx(base_score + w * (0.5 - 0.35), abs=2e-6)
