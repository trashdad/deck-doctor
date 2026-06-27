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
