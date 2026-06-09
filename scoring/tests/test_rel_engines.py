import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from relationships.engines import mine_engines, has_cycle  # noqa: E402


def _R(prod, cons):
    return {"produces": set(prod), "consumes": set(cons)}


def test_mine_finds_three_card_chain():
    # maker -> sac_outlet(consumes fodder=token, produces death) -> aristocrat(consumes death)
    res = {
        "maker": _R(["token"], []),
        "outlet": _R(["death_event"], ["token"]),
        "aristocrat": _R([], ["death_event"]),
    }
    engines = mine_engines(res, kmax=5)
    members = [frozenset(e["members"]) for e in engines]
    assert frozenset({"maker", "outlet", "aristocrat"}) in members


def test_has_cycle_detects_untap_mana_loop():
    # A taps for mana (consumes untap, produces mana); B untaps A (consumes mana, produces untap)
    res = {
        "A": _R(["mana"], ["untap"]),
        "B": _R(["untap"], ["mana"]),
    }
    assert has_cycle(["A", "B"], res) is True


def test_no_cycle_for_pure_chain():
    res = {"maker": _R(["token"], []), "payoff": _R([], ["token"])}
    assert has_cycle(["maker", "payoff"], res) is False
