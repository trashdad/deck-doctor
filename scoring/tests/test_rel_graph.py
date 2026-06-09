import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from relationships.graph import candidate_pairs, neighbors_out  # noqa: E402


def _R(prod, cons):
    return {"produces": set(prod), "consumes": set(cons)}


def test_candidate_pairs_links_producer_to_consumer():
    res = {
        "maker": _R(["token"], []),
        "payoff": _R([], ["token"]),
        "unrelated": _R(["mana"], []),
    }
    pairs = candidate_pairs(res)
    assert ("maker", "payoff") in pairs or ("payoff", "maker") in pairs
    # unrelated mana producer has no consumer -> no pair
    assert all("unrelated" not in p for p in pairs)


def test_neighbors_out_directed_by_resource_flow():
    res = {"maker": _R(["token"], []), "payoff": _R([], ["token"])}
    outs = neighbors_out("maker", res)
    assert "payoff" in outs
    assert neighbors_out("payoff", res) == set()
