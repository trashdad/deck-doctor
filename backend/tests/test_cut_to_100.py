"""cut_to_100 — role/curve-aware cuts against a tiny fake Store (pure; no DB)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.cut_to_100 import CURVE_IDEAL, cut_to_100  # noqa: E402
from app.doctor import DECK_SIZE  # noqa: E402


class _Store:
    """Only the surface suggest_cuts / cut_to_100 read."""

    def __init__(self, cards, edh=None, staple=None, combos=(), engines=()):
        self._cards, self._edh = cards, edh or {}
        self._staple, self._combos = staple or {}, list(combos)
        self._engines = list(engines)

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
        return {"combos": [{"members": m} for m in self._engines]}


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
    cards = {"cmd": CMD, "a": _card("a", "Piece A"), "b": _card("b", "Piece B"),
             "u": _card("u", "Free Bear")}
    res = cut_to_100(_Store(cards, combos=[["a", "b"]]), "cmd", ["a", "b", "u"],
                     template=TPL, target=3)
    # The unprotected card IS cut (so the test is not vacuous); the pieces are not.
    assert _ids(res["cuts"]) == ["u"] and res["shortfall"] == 2


# Type lines as in data/cards.json (spellbook combo 69-2182-3858).
_DEPTHS = _card("depths", "Dark Depths", 0.0, "Legendary Snow Land")
_STAGE = _card("stage", "Thespian's Stage", 0.0, "Land")
_ARIA = _card("aria", "Mayael's Aria", 3.0, "Enchantment")


def test_land_combo_members_are_never_proposed():
    """Review H1: suggest_cuts skips lands before its protected set matters, so the
    land pieces of a complete combo used to come back as cuts."""
    cards = {"cmd": CMD, "depths": _DEPTHS, "stage": _STAGE, "aria": _ARIA}
    store = _Store(cards, combos=[["depths", "stage", "aria"]])
    res = cut_to_100(store, "cmd", ["depths", "stage", "aria"],
                     template={"land": 0}, target=2)
    assert res["cuts"] == [] and res["shortfall"] == 2


def test_engine_land_members_are_never_proposed():
    cards = {"cmd": CMD, "depths": _DEPTHS, "stage": _STAGE}
    store = _Store(cards, engines=[["depths", "stage"]])
    res = cut_to_100(store, "cmd", ["depths", "stage"], template={"land": 0}, target=1)
    assert res["cuts"] == [] and res["shortfall"] == 1


def test_partner_ids_count_toward_size_and_are_never_cut():
    """Review H2: a second command-zone card (partner / background) scored 0 and was
    the recommended cut."""
    cards = {"cmd": CMD, "partner": _card("partner", "Partner", 3.0,
                                          "Legendary Creature — Human"),
             "u1": _card("u1", "Bear", 2.0)}
    res = cut_to_100(_Store(cards, {"u1": (0.0, 0.4)}), "cmd", ["u1"],
                     partner_ids=["partner"], template=TPL, target=2)
    assert _ids(res["cuts"]) == ["u1"] and res["shortfall"] == 1
    assert res["over_by"] == 1 + 1 + 1 - DECK_SIZE


def _hundred_spells():
    cards = {"cmd": CMD}
    for i in range(DECK_SIZE - 1):
        cards[f"s{i}"] = _card(f"s{i}", f"Spell {i}", float(i % 7))
    return cards, [f"s{i}" for i in range(DECK_SIZE - 1)]


def test_unknown_ids_do_not_count_toward_100_and_are_reported():
    """Review M1: ids missing from the store inflated over_by and real cards were cut."""
    cards, deck = _hundred_spells()
    res = cut_to_100(_Store(cards), "cmd", deck + ["ghost1", "ghost2", "ghost1", "ghost3"])
    assert res["over_by"] == 0 and res["cuts"] == [] and res["shortfall"] == 0
    assert res["unknown_ids"] == ["ghost1", "ghost2", "ghost3"]
    assert cut_to_100(_Store(cards), "cmd", deck)["unknown_ids"] == []


@pytest.mark.parametrize("key", ["counters", "tokens", "synergy", "bogus"])
def test_template_keys_outside_the_five_roles_are_rejected(key):
    """Review M2: these keys reached _ROLE_LABEL and raised KeyError (HTTP 500)."""
    cards = {"cmd": CMD, "c": _card("c", "Counter Guy", 2.0, tags=["counter_plus1"])}
    with pytest.raises(ValueError, match=key):
        cut_to_100(_Store(cards), "cmd", ["c"], template={key: 1}, target=1)


def test_spell_with_a_land_back_face_is_ranked_as_a_spell():
    """Review M3: 'Sorcery // Land' was a land (staple-only score, no curve bin)."""
    mdfc = _card("mdfc", "Bala Ged Recovery // Bala Ged Sanctuary", 3.0, "Sorcery // Land")
    mdfc["card_faces"] = [{"type_line": "Sorcery"}, {"type_line": "Land"}]
    cards = {"cmd": CMD, "mdfc": mdfc,
             "l1": _card("l1", "Land 1", 0.0, "Land"), "l2": _card("l2", "Land 2", 0.0, "Land"),
             "u1": _card("u1", "Bear", 2.0)}
    edh = {"mdfc": (0.0, 0.9), "u1": (0.0, 0.4)}
    store = _Store(cards, edh, staple={"l1": 0.8, "l2": 0.8})
    res = cut_to_100(store, "cmd", ["mdfc", "l1", "l2", "u1"], template=TPL, target=1)
    assert res["roles_before"]["land"] == 2
    assert _ids(res["cuts"]) == ["u1"]
    res2 = cut_to_100(store, "cmd", ["mdfc", "l1", "l2", "u1"], template=TPL, target=2)
    mcut = res2["cuts"][1]
    assert mcut["card_id"] == "mdfc" and mcut["role"] == "utility"
    assert mcut["curve_bin"] == 3 and mcut["contribution"] > 0
    # No card_faces: the front of the type line still decides.
    bare = dict(mdfc)
    del bare["card_faces"]
    cards["mdfc"] = bare
    res3 = cut_to_100(_Store(cards, edh, staple={"l1": 0.8, "l2": 0.8}), "cmd",
                      ["mdfc", "l1", "l2", "u1"], template=TPL, target=1)
    assert res3["roles_before"]["land"] == 2 and _ids(res3["cuts"]) == ["u1"]


@pytest.mark.parametrize("cmc,bin_", [(float("nan"), 0), (-1.5, 0), (float("inf"), 6),
                                      (float("-inf"), 0), ("3", 0), (None, 0)])
def test_corrupt_cmc_does_not_raise(cmc, bin_):
    """Review L2: NaN -> ValueError, negative -> KeyError(-1) in CURVE_IDEAL."""
    cards = {"cmd": CMD, "x": _card("x", "Broken", cmc), "y": _card("y", "Fine", 2.0)}
    res = cut_to_100(_Store(cards, {"y": (0.0, 0.9)}), "cmd", ["x", "y"],
                     template=TPL, target=1)
    assert res["cuts"][0]["card_id"] == "x" and res["cuts"][0]["curve_bin"] == bin_


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
            "cards": [{"id": "forest", "zone": "Lands", "quantity": 99},
                      {"id": "r1", "zone": "Ramp"}, {"id": "u1", "zone": "Utility"}]}

    old = client.post("/deck/cuts", json=body).json()
    assert set(old) == {"cuts", "over_by", "target", "shortfall", "unknown_ids"}
    assert old["over_by"] is None and old["target"] is None and old["shortfall"] is None
    assert old["unknown_ids"] is None
    assert [c["card"]["id"] for c in old["cuts"]] == ["u1", "r1"]   # lands never listed
    assert all(c["role"] is None and c["reason"] is None for c in old["cuts"])

    new = client.post("/deck/cuts?to_100=true", json=body).json()
    assert new["over_by"] == 2 and new["target"] == 2 and new["shortfall"] == 0
    assert [c["card"]["id"] for c in new["cuts"]] == ["forest", "forest"]
    assert all(c["role"] == "land" and c["curve_bin"] is None
               and c["breaks_quota"] is False and c["reason"] for c in new["cuts"])
    assert [c["quota_after"] for c in new["cuts"]] == [98, 97]

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


def test_weights_are_overridable_and_zero_weights_fall_back_to_pure_weakness():
    # Removal is 2 over a quota of 1; the draw spell is the (slightly) weaker card.
    cards = {
        "cmd": CMD,
        "k1": _card("k1", "Kill 1", 2.0, "Instant", ["removal"]),
        "k2": _card("k2", "Kill 2", 2.0, "Instant", ["removal"]),
        "k3": _card("k3", "Kill 3", 2.0, "Instant", ["removal"]),
        "u1": _card("u1", "Bear", 2.0),
    }
    edh = {"k1": (0.0, 0.30), "k2": (0.0, 0.30), "k3": (0.0, 0.30), "u1": (0.0, 0.28)}
    store = _Store(cards, edh)
    # Role/curve terms off: plain weakness order, the bear goes first.
    pure = cut_to_100(store, "cmd", list(edh), template=TPL, target=1, role_w=0.0, curve_w=0.0)
    assert _ids(pure["cuts"]) == ["u1"]
    # A large role weight makes the over-full removal suite pay first.
    heavy = cut_to_100(store, "cmd", list(edh), template=TPL, target=1, role_w=1.0, curve_w=0.0)
    assert _ids(heavy["cuts"]) == ["k1"]


def test_default_weights_are_the_module_constants():
    import app.cut_to_100 as mod
    cards = {"cmd": CMD, **{f"u{i}": _card(f"u{i}", f"U{i}", float(i % 7)) for i in range(12)}}
    edh = {f"u{i}": (0.0, i / 50) for i in range(12)}
    store = _Store(cards, edh)
    a = cut_to_100(store, "cmd", list(edh), template=TPL, target=4)
    b = cut_to_100(store, "cmd", list(edh), template=TPL, target=4,
                   role_w=mod.ROLE_W, curve_w=mod.CURVE_W)
    assert a == b


# ---- route-level regressions (review 2026-11-24) ------------------------------

def _client(monkeypatch, store):
    from fastapi.testclient import TestClient
    import app.main as main_mod
    monkeypatch.setattr(main_mod, "get_store", lambda: store)
    return TestClient(main_mod.app, raise_server_exceptions=False)


def test_route_never_cuts_a_commanders_zone_partner(monkeypatch):
    """Review H2 on the route: partner in zone Commanders, target=1."""
    cards = {"cmd": CMD,
             "partner": _card("partner", "Partner", 3.0, "Legendary Creature — Human"),
             "u1": _card("u1", "Bear", 2.0), "u2": _card("u2", "Bear 2", 2.0)}
    client = _client(monkeypatch, _Store(cards, {"u1": (0.0, 0.4), "u2": (0.0, 0.5)}))
    body = {"commander_id": "cmd", "template": TPL,
            "cards": [{"id": "cmd", "zone": "Commanders"},
                      {"id": "partner", "zone": "Commanders"},
                      {"id": "u1", "zone": "Utility"}, {"id": "u2", "zone": "Utility"}]}
    r = client.post("/deck/cuts?to_100=true&target=3", json=body)
    assert r.status_code == 200
    res = r.json()
    assert [c["card"]["id"] for c in res["cuts"]] == ["u1", "u2"] and res["shortfall"] == 1
    assert res["over_by"] == 4 - DECK_SIZE          # cmd + partner + 2


def test_route_reports_unknown_ids_and_ignores_them_for_size(monkeypatch):
    cards, deck = _hundred_spells()
    client = _client(monkeypatch, _Store(cards))
    body = {"commander_id": "cmd",
            "cards": [{"id": c} for c in deck] + [{"id": "ghost", "quantity": 3}]}
    res = client.post("/deck/cuts?to_100=true", json=body).json()
    assert res["over_by"] == 0 and res["cuts"] == [] and res["unknown_ids"] == ["ghost"]
    # default mode response shape is unchanged (no unknown_ids reported there)
    assert client.post("/deck/cuts", json=body).json().get("unknown_ids") is None


@pytest.mark.parametrize("key", ["counters", "tokens", "synergy"])
def test_route_rejects_template_keys_outside_the_five_roles(monkeypatch, key):
    cards = {"cmd": CMD, "c": _card("c", "Counter Guy", 2.0, tags=["counter_plus1"])}
    client = _client(monkeypatch, _Store(cards))
    body = {"commander_id": "cmd", "template": {key: 1}, "cards": [{"id": "c"}]}
    r = client.post("/deck/cuts?to_100=true&target=1", json=body)
    assert r.status_code == 422 and key in r.json()["detail"]


@pytest.mark.parametrize("qty", [0, -1, 100])
def test_route_rejects_out_of_range_quantity(monkeypatch, qty):
    """Review M4: quantity 0 was expanded to one card; no upper bound."""
    cards = {"cmd": CMD, "u1": _card("u1", "Bear")}
    client = _client(monkeypatch, _Store(cards))
    body = {"commander_id": "cmd", "cards": [{"id": "u1", "quantity": qty}]}
    assert client.post("/deck/cuts?to_100=true", json=body).status_code == 422


def test_route_caps_total_expanded_cards(monkeypatch):
    cards = {"cmd": CMD, "forest": _card("forest", "Forest", 0.0, "Basic Land — Forest")}
    client = _client(monkeypatch, _Store(cards))
    big = {"commander_id": "cmd", "cards": [{"id": "forest", "quantity": 99}] * 4}  # 396
    r = client.post("/deck/cuts?to_100=true", json=big)
    assert r.status_code == 400 and "300" in r.json()["detail"]
    ok = {"commander_id": "cmd", "cards": [{"id": "forest", "quantity": 99}] * 3}   # 297
    assert client.post("/deck/cuts?to_100=true", json=ok).status_code == 200


@pytest.mark.parametrize("cmc", [-1.5, float("nan")])
def test_route_corrupt_cmc_is_not_a_500(monkeypatch, cmc):
    cards = {"cmd": CMD, "x": _card("x", "Broken", cmc)}
    client = _client(monkeypatch, _Store(cards))
    body = {"commander_id": "cmd", "cards": [{"id": "x"}]}
    r = client.post("/deck/cuts?to_100=true&target=1", json=body)
    assert r.status_code == 200 and r.json()["cuts"][0]["curve_bin"] == 0


def test_route_default_mode_never_lists_a_commanders_zone_partner(monkeypatch):
    cards = {"cmd": CMD,
             "partner": _card("partner", "Partner", 3.0, "Legendary Creature — Human"),
             "u1": _card("u1", "Bear", 2.0)}
    client = _client(monkeypatch, _Store(cards, {"u1": (0.0, 0.4)}))
    body = {"commander_id": "cmd",
            "cards": [{"id": "cmd", "zone": "Commanders"}, {"id": "partner", "zone": "Commanders"},
                      {"id": "u1", "zone": "Utility"}]}
    res = client.post("/deck/cuts?limit=1", json=body).json()
    assert [c["card"]["id"] for c in res["cuts"]] == ["u1"]
