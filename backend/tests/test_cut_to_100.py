"""cut_to_100 — role/curve-aware cuts against a tiny fake Store (pure; no DB)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.cut_to_100 import CURVE_IDEAL, cut_to_100  # noqa: E402
from app.doctor import DECK_SIZE  # noqa: E402


class _Store:
    """Only the surface suggest_cuts / cut_to_100 read."""

    def __init__(self, cards, edh=None, staple=None, combos=()):
        self._cards, self._edh = cards, edh or {}
        self._staple, self._combos = staple or {}, list(combos)

    def get(self, cid):
        return self._cards.get(cid)

    def staple_score(self, cid):
        return self._staple.get(cid, 0.0)

    def edhrec_for(self, _cmd):
        return self._edh

    def cooccurrence_neighbors(self, _cid, _k):
        return []

    def synergy_neighbors(self, _cid, _k):
        return []

    def deck_spellbook(self, _ids):
        return {"complete": [{"members": m} for m in self._combos], "near": []}

    def deck_engines(self, _ids):
        return {"combos": []}


def _card(cid, name, cmc=2.0, type_line="Creature — Bear", tags=()):
    return {"id": cid, "name": name, "cmc": cmc, "type_line": type_line,
            "mechanic_tags": list(tags)}


CMD = _card("cmd", "Commander", 4.0, "Legendary Creature — Elf")
# Tiny template so fixtures of a dozen cards have meaningful quotas.
TPL = {"land": 2, "ramp": 2, "card_draw": 1, "removal": 1, "board_wipe": 0}


def _ids(cuts):
    return [c["card_id"] for c in cuts]


def test_exactly_over_by_cuts_and_never_the_commander():
    cards = {"cmd": CMD}
    deck = []
    for i in range(DECK_SIZE + 2):          # 1 + 102 = 103 cards → over by 3
        cid = f"u{i}"
        cards[cid] = _card(cid, f"Utility {i}", cmc=float(i % 7))
        deck.append(cid)
    edh = {cid: (0.0, i / 200) for i, cid in enumerate(deck)}   # u0 weakest … u101 strongest
    res = cut_to_100(_Store(cards, edh), "cmd", deck + ["cmd"])
    assert res["over_by"] == 3 and res["target"] == 3 and res["shortfall"] == 0
    assert len(res["cuts"]) == 3
    assert "cmd" not in _ids(res["cuts"])
    assert all(not c["breaks_quota"] for c in res["cuts"])
    assert all(c["reason"].endswith(".") and c["role"] == "utility" for c in res["cuts"])


def test_deck_at_or_under_100_proposes_nothing_by_default():
    cards = {"cmd": CMD, "a": _card("a", "A")}
    res = cut_to_100(_Store(cards), "cmd", ["a"])
    assert res["over_by"] < 0 and res["cuts"] == [] and res["target"] == 0


def test_weak_ramp_at_quota_is_kept_and_stronger_utility_cut_instead():
    cards = {
        "cmd": CMD,
        "r1": _card("r1", "Weak Rock", 2.0, "Artifact", ["ramp"]),
        "r2": _card("r2", "Weak Rock 2", 2.0, "Artifact", ["ramp"]),
        "u1": _card("u1", "Decent Bear", 2.0),
    }
    edh = {"r1": (0.0, 0.02), "r2": (0.0, 0.03), "u1": (0.3, 0.40)}
    res = cut_to_100(_Store(cards, edh), "cmd", ["r1", "r2", "u1"], template=TPL, target=1)
    cut = res["cuts"][0]
    assert cut["card_id"] == "u1"           # ramp is exactly at quota 2 → protected
    assert cut["breaks_quota"] is False
    assert res["roles_after"]["ramp"] == 2


def test_quota_break_is_last_resort_and_flagged():
    cards = {
        "cmd": CMD,
        "r1": _card("r1", "Rock A", 2.0, "Artifact", ["ramp"]),
        "r2": _card("r2", "Rock B", 3.0, "Artifact", ["ramp"]),
    }
    edh = {"r1": (0.0, 0.10), "r2": (0.0, 0.50)}
    res = cut_to_100(_Store(cards, edh), "cmd", ["r1", "r2"], template=TPL, target=1)
    cut = res["cuts"][0]
    assert cut["card_id"] == "r1" and cut["breaks_quota"] is True
    assert cut["role_before"] == 2 and cut["role_after"] == 1 and cut["quota"] == 2
    assert "below the template's 2" in cut["reason"]
    assert res["shortfall"] == 0


def test_role_surplus_prefers_cut_from_overfull_role():
    # Same weakness; removal is 2 over its quota of 1, card_draw is exactly at quota.
    cards = {
        "cmd": CMD,
        "k1": _card("k1", "Kill 1", 2.0, "Instant", ["removal"]),
        "k2": _card("k2", "Kill 2", 2.0, "Instant", ["removal"]),
        "k3": _card("k3", "Kill 3", 2.0, "Instant", ["removal"]),
        "d1": _card("d1", "Draw 1", 2.0, "Sorcery", ["card_draw"]),
        "d2": _card("d2", "Draw 2", 2.0, "Sorcery", ["card_draw"]),
    }
    edh = {c: (0.0, 0.20) for c in ("k1", "k2", "k3", "d1", "d2")}
    res = cut_to_100(_Store(cards, edh), "cmd", list(edh), template=TPL, target=3)
    first, second, third = res["cuts"]
    assert first["card_id"] == "k1"           # Removal 3/1 is the most overfull role
    assert first["role_before"] == 3 and first["role_after"] == 2
    assert "Removal 3 → 2 stays at or above the template's 1" in first["reason"]
    # Now Removal 2/1 and Card Draw 2/1 are equally over quota: one from each goes
    # next, in id order, and neither breaks its quota.
    assert {second["card_id"], third["card_id"]} == {"d1", "k2"}
    assert all(c["role_before"] == 2 and c["role_after"] == 1 and not c["breaks_quota"]
               for c in (second, third))
    assert res["roles_after"] == {"land": 0, "ramp": 0, "card_draw": 1, "removal": 1,
                                  "board_wipe": 0, "utility": 0}


def test_curve_overload_breaks_ties_toward_the_fat_bin():
    # Identical weakness and role; the 6+ bin holds 3 of 5 nonlands (ideal 11 %).
    cards = {"cmd": CMD}
    deck = []
    for cid, cmc in (("f1", 7.0), ("f2", 6.0), ("f3", 8.0), ("c1", 2.0), ("c2", 3.0)):
        cards[cid] = _card(cid, cid.upper(), cmc)
        deck.append(cid)
    edh = {c: (0.0, 0.20) for c in deck}
    res = cut_to_100(_Store(cards, edh), "cmd", deck, template=TPL, target=1)
    cut = res["cuts"][0]
    assert cut["curve_bin"] == 6 and cut["card_id"] in {"f1", "f2", "f3"}
    assert cut["curve_before"] == 3 and cut["curve_after"] == 2
    assert cut["curve_ideal"] == round(CURVE_IDEAL[6] * 5, 1)   # 5 nonlands → 0.6
    assert "cmc 6+: that bin goes 3 → 2" in cut["reason"]


def test_surplus_lands_are_cut_basics_first_and_copies_decrement():
    cards = {
        "cmd": CMD,
        "forest": _card("forest", "Forest", 0.0, "Basic Land — Forest"),
        "nonb": _card("nonb", "Fancy Land", 0.0, "Land"),
        "u1": _card("u1", "Bear", 2.0),
        "u2": _card("u2", "Bear 2", 3.0),
    }
    deck = ["forest", "forest", "forest", "nonb", "u1", "u2"]   # 4 lands vs quota 2
    edh = {"u1": (0.0, 0.20), "u2": (0.1, 0.40)}
    staple = {"nonb": 0.9}
    res = cut_to_100(_Store(cards, edh, staple), "cmd", deck, template=TPL, target=2)
    assert _ids(res["cuts"]) == ["forest", "forest"]
    assert [c["role_before"] for c in res["cuts"]] == [4, 3]
    assert res["roles_after"]["land"] == 2
    assert all(c["curve_bin"] is None and not c["breaks_quota"] for c in res["cuts"])
    # Third cut: lands are now at quota, so the weak bear goes before any land.
    res3 = cut_to_100(_Store(cards, edh, staple), "cmd", deck, template=TPL, target=3)
    assert _ids(res3["cuts"]) == ["forest", "forest", "u1"]


def test_lands_at_quota_are_protected_over_a_weak_spell():
    cards = {
        "cmd": CMD,
        "l1": _card("l1", "Land 1", 0.0, "Land"),
        "l2": _card("l2", "Land 2", 0.0, "Land"),
        "u1": _card("u1", "Bear", 2.0),
    }
    res = cut_to_100(_Store(cards, {"u1": (0.0, 0.9)}), "cmd", ["l1", "l2", "u1"],
                     template=TPL, target=1)
    assert _ids(res["cuts"]) == ["u1"] and not res["cuts"][0]["breaks_quota"]


def test_combo_members_are_never_proposed_and_shortfall_is_reported():
    cards = {"cmd": CMD, "a": _card("a", "Piece A"), "b": _card("b", "Piece B")}
    res = cut_to_100(_Store(cards, combos=[["a", "b"]]), "cmd", ["a", "b"],
                     template=TPL, target=2)
    assert res["cuts"] == [] and res["shortfall"] == 2


def test_route_default_mode_unchanged_and_to_100_flag_adds_fields(monkeypatch):
    """/deck/cuts: without the flag the response is exactly the old shape; with
    to_100=true the cut rows carry role/curve/reason fields and the header counts."""
    from fastapi.testclient import TestClient
    import app.main as main_mod

    cards = {
        "cmd": CMD,
        "forest": _card("forest", "Forest", 0.0, "Basic Land — Forest"),
        "r1": _card("r1", "Rock", 2.0, "Artifact", ["ramp"]),
        "u1": _card("u1", "Bear", 2.0),
    }
    fake = _Store(cards, {"u1": (0.0, 0.05), "r1": (0.0, 0.60)})
    monkeypatch.setattr(main_mod, "get_store", lambda: fake)
    client = TestClient(main_mod.app)
    body = {"commander_id": "cmd", "template": TPL,
            "cards": [{"id": "forest", "zone": "Lands", "quantity": 100},
                      {"id": "r1", "zone": "Ramp"}, {"id": "u1", "zone": "Utility"}]}

    old = client.post("/deck/cuts", json=body).json()
    assert set(old) == {"cuts", "over_by", "target", "shortfall"}
    assert old["over_by"] is None and old["target"] is None and old["shortfall"] is None
    assert [c["card"]["id"] for c in old["cuts"]] == ["u1", "r1"]   # lands never listed
    assert all(c["role"] is None and c["reason"] is None for c in old["cuts"])

    new = client.post("/deck/cuts?to_100=true", json=body).json()
    assert new["over_by"] == 3 and new["target"] == 3 and new["shortfall"] == 0
    assert [c["card"]["id"] for c in new["cuts"]] == ["forest", "forest", "forest"]
    assert all(c["role"] == "land" and c["curve_bin"] is None
               and c["breaks_quota"] is False and c["reason"] for c in new["cuts"])
    assert [c["quota_after"] for c in new["cuts"]] == [99, 98, 97]

    one = client.post("/deck/cuts?to_100=true&target=1", json=body).json()
    assert one["target"] == 1 and len(one["cuts"]) == 1
    assert client.post("/deck/cuts?to_100=true&target=0", json=body).status_code == 422


def test_cut_keeps_suggest_cuts_signals_and_adds_role_fields():
    cards = {"cmd": CMD, "x": _card("x", "Off-plan", 3.0)}
    res = cut_to_100(_Store(cards, {"x": (-0.15, 0.50)}), "cmd", ["x"], template=TPL, target=1)
    cut = res["cuts"][0]
    assert {r["signal"] for r in cut["reasons"]} >= {"edhrec", "cooccurrence", "synergy"}
    assert "-0.15" in cut["reason"] and "50%" in cut["reason"]
    assert cut["quota_after"] == cut["role_after"] == 0 and cut["role"] == "utility"
