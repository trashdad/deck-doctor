"""SP5 suggestion engine tests against the real store (scores.sqlite + edhrec.sqlite)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.store import get_store  # noqa: E402
from app.suggest import BANLIST, is_commander  # noqa: E402

client = TestClient(app)
store = get_store()


def _id(name: str) -> str:
    cid = store._name_to_id.get(name.lower())
    assert cid, f"card not found: {name!r}"
    return cid


def _recommend(commander_id, cards=(), limit=12, explain=False):
    qs = f"?limit={limit}&explain={'true' if explain else 'false'}"
    return client.post(
        f"/deck/recommend{qs}",
        json={"commander_id": commander_id,
              "cards": [{"id": c} for c in cards]},
    )


def test_golden_edhrec_commander_empty_deck():
    """An EDHREC-covered commander with an empty deck gets its signature list."""
    cmd = _id("The Ur-Dragon")
    assert cmd in store._edhrec, "Ur-Dragon should have EDHREC rows after the rebuild"
    r = _recommend(cmd, limit=20)
    assert r.status_code == 200
    body = r.json()
    assert body["tier"] == "edhrec"
    suggestions = body["suggestions"]
    assert len(suggestions) >= 10
    scores = [s["score"] for s in suggestions]
    assert scores == sorted(scores, reverse=True)
    for s in suggestions:
        assert "Basic" not in s["card"]["type_line"]
        assert s["card"]["name"] not in BANLIST


def test_in_deck_and_commander_never_suggested():
    cmd = _id("The Ur-Dragon")
    deck = list(store._edhrec[cmd].keys())[:5]
    r = _recommend(cmd, deck, limit=30)
    assert r.status_code == 200
    suggested = {s["card"]["id"] for s in r.json()["suggestions"]}
    assert not (suggested & set(deck))
    assert cmd not in suggested


def test_color_identity_filter():
    """Every suggestion fits inside the commander's color identity."""
    # find a non-5-color EDHREC commander so the filter actually bites
    cmd = next(
        (cid for cid in store._edhrec
         if store.get(cid) and len(store.get(cid)["color_identity"]) <= 2),
        None,
    )
    assert cmd, "no narrow-CI commander in edhrec data"
    ci = set(store.get(cmd)["color_identity"])
    r = _recommend(cmd, limit=30)
    assert r.status_code == 200
    for s in r.json()["suggestions"]:
        assert set(s["card"]["color_identity"]) <= ci, s["card"]["name"]


def test_cold_start_commander_without_edhrec():
    """A legal commander absent from EDHREC still gets non-empty suggestions."""
    cmd = next(
        (cid for cid, card in store._cards.items()
         if is_commander(card) and cid not in store._edhrec
         and store.cooccurrence_neighbors(cid, 5)),
        None,
    )
    assert cmd, "no cold-start commander with cooccurrence data found"
    deck = [other for other, _l, _j in store.cooccurrence_neighbors(cmd, 5)]
    r = _recommend(cmd, deck, limit=12)
    assert r.status_code == 200
    body = r.json()
    assert body["tier"] in ("cooccurrence", "color_staple")
    assert len(body["suggestions"]) > 0


def test_obscure_commander_falls_back_to_staples():
    """A commander with no signals at all fills from color staples (never empty)."""
    cmd = next(
        (cid for cid, card in store._cards.items()
         if is_commander(card) and cid not in store._edhrec
         and not store.cooccurrence_neighbors(cid, 1)
         and not store.synergy_neighbors(cid, 1)),
        None,
    )
    if cmd is None:
        pytest.skip("every commander has some signal in this corpus")
    r = _recommend(cmd, limit=12)
    assert r.status_code == 200
    body = r.json()
    assert body["suggestions"], "staple fallback must never return empty"
    assert body["tier"] == "color_staple"


def test_engine_completion_surfaces_missing_piece():
    """Deck = all-but-one member of an asserted combo -> missing piece suggested
    with an engine reason."""
    combo = None
    for eng in store._engines:
        if not eng["asserted"] or len(eng["members"]) < 2:
            continue
        cards = [store.get(m) for m in eng["members"]]
        if any(c is None for c in cards):
            continue
        ci = set().union(*(set(c["color_identity"]) for c in cards))
        missing_card = cards[-1]
        if missing_card["name"] in BANLIST or "Basic" in missing_card["type_line"]:
            continue
        combo = (eng, cards, ci)
        break
    assert combo, "no usable asserted combo in engines table"
    eng, cards, ci = combo
    # a 5-color commander legally covers any combo's color identity
    cmd = _id("The Ur-Dragon")
    deck = [c["id"] for c in cards[:-1]]
    missing = cards[-1]["id"]
    r = _recommend(cmd, deck, limit=60, explain=True)
    assert r.status_code == 200
    by_id = {s["card"]["id"]: s for s in r.json()["suggestions"]}
    assert missing in by_id, "missing combo piece not suggested"
    signals = {reason["signal"] for reason in by_id[missing]["reasons"]}
    assert "engine" in signals


def test_explain_reasons_present_iff_requested():
    cmd = _id("The Ur-Dragon")
    plain = _recommend(cmd, limit=5).json()["suggestions"]
    assert all(s["reasons"] == [] for s in plain)
    explained = _recommend(cmd, limit=5, explain=True).json()["suggestions"]
    assert any(s["reasons"] for s in explained)
    for s in explained:
        for reason in s["reasons"]:
            assert {"signal", "detail", "value"} <= set(reason)


def test_determinism():
    cmd = _id("The Ur-Dragon")
    deck = list(store._edhrec[cmd].keys())[:3]
    a = _recommend(cmd, deck, limit=15, explain=True).json()
    b = _recommend(cmd, deck, limit=15, explain=True).json()
    assert a == b


def test_recommend_requires_commander():
    r = client.post("/deck/recommend", json={"commander_id": None, "cards": []})
    assert r.status_code == 400


def test_recommend_rejects_non_legendary():
    sol = _id("Sol Ring")
    r = client.post("/deck/recommend", json={"commander_id": sol, "cards": []})
    assert r.status_code == 400


# ── EDHREC inclusion in the blend (hub docs/research/2026-10-07-deckdoctor-blend-experiment) ──
# score = (1 − w)·blend + w·inclusion + engine bonus, w = INCLUSION_WEIGHT. The blend is
# EDHREC synergy + co-occurrence + structural synergy; the engine/combo-completion bonus
# stays outside the mix so known combo pieces are not pushed out by popular staples.

def _b0_from_reasons(reasons, has_edh):
    from app.suggest import WEIGHTS
    w = dict(WEIGHTS)
    if not has_edh:
        w["edh"] = 0.0
    v = {r["signal"]: r["value"] for r in reasons}
    tw = sum(w.values())
    blend = (w["edh"] * v.get("edhrec", 0.0) + w["cooc"] * v.get("cooccurrence", 0.0)
             + w["struct"] * v.get("synergy", 0.0)) / tw
    return blend, w["engine"] * v.get("engine", 0.0) / tw


@pytest.mark.parametrize("commander", ["The Ur-Dragon", "Krenko, Mob Boss"])
def test_score_is_b0_mixed_with_edhrec_inclusion(commander):
    from app.suggest import INCLUSION_WEIGHT
    cmd = _id(commander)
    deck = [cid for cid in list(store._edhrec.get(cmd, {}))[:8]]
    body = _recommend(cmd, cards=deck, limit=40, explain=True).json()
    edh = store.edhrec_for(cmd)
    checked = 0
    for s in body["suggestions"]:
        if any(r["signal"] == "staple" for r in s["reasons"]):
            continue
        cid = s["card"]["id"]
        inc = (edh.get(cid) or (0.0, 0.0))[1] or 0.0
        reasons = {r["signal"]: r["value"] for r in s["reasons"]}
        if inc > 0:
            assert reasons.get("edhrec_inclusion") == pytest.approx(round(inc, 4), abs=1e-4)
        blend, engine = _b0_from_reasons(s["reasons"], bool(edh))
        expected = (1 - INCLUSION_WEIGHT) * blend + INCLUSION_WEIGHT * inc + engine
        assert s["score"] == pytest.approx(expected, abs=2e-4), s["card"]["name"]
        checked += 1
    assert checked >= 20


def test_high_inclusion_card_without_synergy_can_be_suggested():
    # Staples like Sol Ring often have EDHREC synergy <= 0 but high inclusion. The
    # old blend scored them 0 for an empty deck and dropped them.
    cmd = _id("The Ur-Dragon")
    edh = store.edhrec_for(cmd)
    picks = [cid for cid, (syn, inc) in edh.items() if (syn or 0) <= 0 and (inc or 0) >= 0.5]
    assert picks, "expected an Ur-Dragon card with synergy <= 0 and inclusion >= 50%"
    body = _recommend(cmd, limit=60).json()
    got = {s["card"]["id"] for s in body["suggestions"]}
    assert got & set(picks)


def test_unit_clamp_treats_nan_and_none_as_zero():
    from app.suggest import _unit
    assert _unit(float("nan")) == 0.0
    assert _unit(None) == 0.0
    assert _unit(float("inf")) == 0.0
    assert _unit(-0.2) == 0.0 and _unit(1.7) == 1.0 and _unit(0.42) == 0.42


def test_scores_never_increase_down_the_list_including_staple_fill():
    # Staples are a last resort: they must sit below every signal-driven suggestion,
    # even when a weak signal-driven card scores under STAPLE_SCORE.
    cases = []
    for c in ("The Ur-Dragon", "Krenko, Mob Boss"):
        cmd = _id(c)
        cases.append((cmd, list(store._edhrec.get(cmd, {}))[:3]))
    for cid, card in list(store._cards.items()):
        if is_commander(card) and cid not in store._edhrec:
            cases.append((cid, []))
            if len(cases) >= 8:
                break
    filled = 0
    for cmd, deck in cases:
        body = _recommend(cmd, cards=deck, limit=60, explain=True).json()
        scores = [s["score"] for s in body["suggestions"]]
        assert scores == sorted(scores, reverse=True), store.get(cmd)["name"]
        filled += any(r["signal"] == "staple" for s in body["suggestions"] for r in s["reasons"])
    assert filled, "expected at least one case to reach the staple fill"
