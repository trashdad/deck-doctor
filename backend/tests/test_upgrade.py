"""Unit tests for the Card Upgrade Finder ranking (pure, no DB/Store needed)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.upgrade import rank_upgrades, upgrade_sweep  # noqa: E402


def _sig(cid, *, ier, cmc, category, mech, sem, name=None):
    return {
        "id": cid,
        "card": {"id": cid, "name": name or cid},
        "ier": ier,
        "cmc": cmc,
        "category": category,
        "mech": mech,
        "sem": sem,
    }


# Target: a 3-mana single-target removal spell.
TARGET = _sig("target", ier=5.0, cmc=3, category="removal",
              mech=["removal"], sem=["e:destroy"], name="Murder")

CANDS = [
    # Same job, more efficient (cheaper, higher IER).
    _sig("efficient", ier=9.0, cmc=2, category="removal",
         mech=["removal"], sem=["e:destroy"], name="Infernal Grasp"),
    # Same job, same stats — a lateral move.
    _sig("lateral", ier=5.0, cmc=3, category="removal",
         mech=["removal"], sem=["e:destroy"], name="Cast Down"),
    # Multimodal: removes AND makes a token (extra role).
    _sig("flexible", ier=6.0, cmc=3, category="removal",
         mech=["removal", "token_producer"], sem=["e:destroy", "e:create_token"],
         name="Beast Within"),
    # Unrelated: ramp — should be filtered out (does nothing similar).
    _sig("ramp", ier=12.0, cmc=2, category="ramp",
         mech=["ramp"], sem=["e:ramp"], name="Sol Ring"),
]


def _ids(options):
    return [o["card"]["id"] for o in options]


def test_unrelated_card_is_excluded():
    opts = rank_upgrades(TARGET, CANDS, efficiency=0.5)
    assert "ramp" not in _ids(opts)


def test_max_efficiency_promotes_the_efficient_card():
    opts = rank_upgrades(TARGET, CANDS, efficiency=1.0)
    assert opts[0]["card"]["id"] == "efficient"


def test_slider_changes_ranking():
    eff = _ids(rank_upgrades(TARGET, CANDS, efficiency=1.0))
    sim = _ids(rank_upgrades(TARGET, CANDS, efficiency=0.0))
    assert eff != sim  # the slider actually moves results


def test_flexibility_toggle_promotes_multimodal():
    # With flexibility favored, the multimodal card (removal + makes a token) tops
    # the list even at the "closest match" end of the slider.
    flex = rank_upgrades(TARGET, CANDS, efficiency=0.0, favor_flexibility=True)
    assert flex[0]["card"]["id"] == "flexible"


def test_multimodal_not_penalized_for_extra_function():
    # Coverage (not Jaccard): a card that does the target's job PLUS more is still
    # fully similar — its similarity should match a like-for-like replacement.
    opts = {o["card"]["id"]: o for o in rank_upgrades(TARGET, CANDS, efficiency=0.0)}
    assert opts["flexible"]["similarity"] == opts["lateral"]["similarity"]


def test_efficiency_gain_is_reported():
    opts = rank_upgrades(TARGET, CANDS, efficiency=1.0)
    by_id = {o["card"]["id"]: o for o in opts}
    assert by_id["efficient"]["efficiency_gain"] == 4.0
    assert by_id["lateral"]["efficiency_gain"] == 0.0


def test_synergy_toggle_uses_commander_synergy():
    syn = {"lateral": 0.9}  # lateral has strong commander synergy
    boosted = _ids(rank_upgrades(TARGET, CANDS, efficiency=0.0,
                                 favor_synergy=True, synergy=syn))
    plain = _ids(rank_upgrades(TARGET, CANDS, efficiency=0.0,
                               favor_synergy=False, synergy=syn))
    assert boosted.index("lateral") <= plain.index("lateral")


def test_empty_candidates_returns_empty():
    assert rank_upgrades(TARGET, [], efficiency=0.5) == []


# ---- upgrade_sweep orchestration (injected fakes, no DB) ----

class _FakeStore:
    def __init__(self, cards):
        self._c = cards

    def get(self, cid):
        return self._c.get(cid)


def test_sweep_pairs_weak_cards_with_upgrades():
    cards = {
        "weak1": {"id": "weak1", "name": "Filler A"},
        "weak2": {"id": "weak2", "name": "Filler B"},
        "weak3": {"id": "weak3", "name": "Filler C"},
    }
    store = _FakeStore(cards)

    def fake_cuts(_store, _cmd, _deck, limit):
        return [
            {"card_id": "weak1", "contribution": 0.01, "reasons": []},
            {"card_id": "weak2", "contribution": 0.02, "reasons": []},
            {"card_id": "weak3", "contribution": 0.03, "reasons": []},
        ][:limit]

    def fake_upgrades(_store, target_id, _cmd, _deck, **kw):
        # weak2 has no available upgrade — it must be skipped, not emitted empty.
        if target_id == "weak2":
            return {"target": cards[target_id], "options": []}
        return {"target": cards[target_id],
                "options": [{"card": {"id": f"up-{target_id}", "name": "Better"},
                             "score": 0.9, "efficiency_gain": 2.0,
                             "similarity": 1.0, "reasons": []}]}

    out = upgrade_sweep(store, "cmd", ["weak1", "weak2", "weak3"],
                        _cuts=fake_cuts, _upgrades=fake_upgrades)
    targets = [s["target"]["id"] for s in out["swaps"]]
    assert targets == ["weak1", "weak3"]          # weak2 (no options) dropped
    assert out["swaps"][0]["options"][0]["card"]["id"] == "up-weak1"


def test_sweep_respects_max_swaps():
    cards = {f"w{i}": {"id": f"w{i}", "name": f"c{i}"} for i in range(5)}
    store = _FakeStore(cards)

    def fake_cuts(_s, _c, _d, limit):
        return [{"card_id": f"w{i}", "contribution": 0.0, "reasons": []}
                for i in range(5)][:limit]

    def fake_upgrades(_s, tid, _c, _d, **kw):
        return {"target": cards[tid],
                "options": [{"card": {"id": f"u{tid}", "name": "x"}, "score": 1.0,
                             "efficiency_gain": 1.0, "similarity": 1.0, "reasons": []}]}

    out = upgrade_sweep(store, "cmd", list(cards), max_swaps=2,
                        _cuts=fake_cuts, _upgrades=fake_upgrades)
    assert len(out["swaps"]) == 2


def _opt(cid, gain):
    return {"card": {"id": cid, "name": cid}, "score": 1.0, "efficiency_gain": gain,
            "similarity": 1.0, "reasons": []}


class _SynStore(_FakeStore):
    """Fake store that also answers edhrec_for: card -> (synergy, inclusion)."""

    def __init__(self, cards, edh):
        super().__init__(cards)
        self._edh = edh

    def edhrec_for(self, _cmd):
        return self._edh


def test_sweep_only_offers_real_upgrades():
    """Real-data regression: the Tune-up offered Pristine Talisman (−0.9 IER) for
    Talisman of Dominance. A swap must beat the card it replaces — higher IER, or
    stronger commander synergy — otherwise it is a side-grade, not an upgrade."""
    cards = {"weak": {"id": "weak", "name": "Filler"}}
    store = _SynStore(cards, {"weak": (0.05, 0.1), "syn": (0.40, 0.3), "same": (0.05, 0.2)})

    def fake_cuts(_s, _c, _d, limit):
        return [{"card_id": "weak", "contribution": 0.0, "reasons": []}]

    def fake_upgrades(_s, tid, _c, _d, **kw):
        return {"target": cards[tid],
                "options": [_opt("worse", -0.9), _opt("same", 0.0),
                            _opt("syn", -0.5), _opt("better", 1.5)]}

    out = upgrade_sweep(store, "cmd", ["weak"], _cuts=fake_cuts, _upgrades=fake_upgrades)
    assert [o["card"]["id"] for o in out["swaps"][0]["options"]] == ["syn", "better"]


def test_sweep_skips_card_with_only_downgrades_and_trims_to_per_card():
    cards = {"a": {"id": "a", "name": "A"}, "b": {"id": "b", "name": "B"}}
    store = _SynStore(cards, {})
    seen_kw = []

    def fake_cuts(_s, _c, _d, limit):
        return [{"card_id": "a", "contribution": 0.0, "reasons": []},
                {"card_id": "b", "contribution": 0.1, "reasons": []}]

    def fake_upgrades(_s, tid, _c, _d, **kw):
        seen_kw.append(kw)
        if tid == "a":
            return {"target": cards[tid], "options": [_opt("a-worse", -1.0)]}
        return {"target": cards[tid],
                "options": [_opt("b1", 2.0), _opt("b-worse", -2.0), _opt("b2", 1.0)]}

    out = upgrade_sweep(store, "cmd", ["a", "b"], per_card=1,
                        _cuts=fake_cuts, _upgrades=fake_upgrades)
    assert [s["target"]["id"] for s in out["swaps"]] == ["b"]   # a had only downgrades
    assert [o["card"]["id"] for o in out["swaps"][0]["options"]] == ["b1"]
    # filtering happens inside the ranker, before its limit, so it can't starve
    assert all(kw["upgrades_only"] is True and kw["limit"] == 1 for kw in seen_kw)


# ---- review fixes (2026-10-05) ----

def test_unknown_target_ier_is_not_an_efficiency_gain():
    """Review #1: with no target IER, `ier or 0.0` made every candidate's own IER
    look like a gain, so everything passed the Tune-up's "real upgrade" filter."""
    target = dict(TARGET, ier=None)
    opts = rank_upgrades(target, CANDS, efficiency=0.5)
    assert opts and all(o["efficiency_gain"] is None for o in opts)
    assert not any(r["signal"] == "efficiency" for o in opts for r in o["reasons"])


def test_unknown_candidate_ier_is_not_an_efficiency_gain():
    cands = [dict(c, ier=None) if c["id"] == "efficient" else c for c in CANDS]
    by_id = {o["card"]["id"]: o for o in rank_upgrades(TARGET, cands, efficiency=0.5)}
    assert by_id["efficient"]["efficiency_gain"] is None
    assert by_id["lateral"]["efficiency_gain"] == 0.0


def test_upgrades_only_filters_before_the_limit():
    """Review #5: the upgrades-only predicate must apply before truncation, or a
    low-similarity genuine upgrade is cut by blended score before it is seen."""
    downgrades = [_sig(f"down{i}", ier=3.0, cmc=3, category="removal",
                       mech=["removal"], sem=["e:destroy"]) for i in range(12)]
    upgrade = _sig("upgrade", ier=9.0, cmc=6, category="removal",
                   mech=["removal"], sem=[])
    plain = _ids(rank_upgrades(TARGET, downgrades + [upgrade], efficiency=0.4, limit=4))
    assert "upgrade" not in plain                      # precondition: it ranks low
    only = rank_upgrades(TARGET, downgrades + [upgrade], efficiency=0.4, limit=4,
                         upgrades_only=True)
    assert _ids(only) == ["upgrade"]


def test_upgrades_only_keeps_unknown_ier_with_more_synergy():
    target = dict(TARGET, ier=None)
    cands = [_sig("syn", ier=4.0, cmc=3, category="removal", mech=["removal"], sem=["e:destroy"]),
             _sig("nosyn", ier=9.0, cmc=3, category="removal", mech=["removal"], sem=["e:destroy"])]
    only = rank_upgrades(target, cands, efficiency=0.5, synergy={"syn": 0.4},
                         upgrades_only=True)
    assert _ids(only) == ["syn"]                       # IER unknown -> synergy decides


class _SweepStore:
    """Store surface used by the REAL find_upgrades path (no DB)."""

    def __init__(self, cards, pool_ids, edh=None):
        self._c, self._pool, self._edh = cards, pool_ids, edh or {}

    def get(self, cid):
        return self._c.get(cid)

    def similar_cards(self, _cid, limit=20):
        return [self._c[i] for i in self._pool][:limit]

    def edhrec_for(self, _cmd):
        return self._edh


def _card(cid, *, ier, cmc, mech, sem, ci=("B",)):
    return {"id": cid, "name": cid, "type_line": "Instant", "color_identity": list(ci),
            "ier": ier, "cmc": cmc, "mechanic_tags": list(mech), "semantic_tags": list(sem)}


def _weak_cut(_s, _c, _d, limit):
    return [{"card_id": "weak", "contribution": 0.0, "reasons": []}]


def test_sweep_real_ranking_finds_low_similarity_upgrade():
    """Review #5 end-to-end through rank_upgrades (no stubbed _upgrades)."""
    cards = {"cmd": _card("cmd", ier=1.0, cmc=4, mech=[], sem=[]),
             "weak": _card("weak", ier=5.0, cmc=3, mech=["removal"], sem=["e:destroy"])}
    pool = []
    for i in range(12):
        cards[f"down{i}"] = _card(f"down{i}", ier=3.0, cmc=3, mech=["removal"], sem=["e:destroy"])
        pool.append(f"down{i}")
    cards["upgrade"] = _card("upgrade", ier=9.0, cmc=6, mech=["removal"], sem=[])
    pool.append("upgrade")
    out = upgrade_sweep(_SweepStore(cards, pool), "cmd", ["weak"], per_card=1,
                        _cuts=_weak_cut)
    assert [s["target"]["id"] for s in out["swaps"]] == ["weak"]
    assert [o["card"]["id"] for o in out["swaps"][0]["options"]] == ["upgrade"]


def test_sweep_real_ranking_unknown_target_ier_needs_synergy():
    cards = {"cmd": _card("cmd", ier=1.0, cmc=4, mech=[], sem=[]),
             "weak": _card("weak", ier=None, cmc=3, mech=["removal"], sem=["e:destroy"]),
             "other": _card("other", ier=8.0, cmc=3, mech=["removal"], sem=["e:destroy"])}
    out = upgrade_sweep(_SweepStore(cards, ["other"]), "cmd", ["weak"], _cuts=_weak_cut)
    assert out["swaps"] == []
