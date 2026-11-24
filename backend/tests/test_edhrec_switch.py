"""DECKDOCTOR_EDHREC_SIGNAL kill switch (docs/plans/2026-11-24-edhrec-compliance.md).

Default 'on' = today's behaviour. 'off' = edhrec_for() returns {} for every
commander and the suggester degrades to its existing co-occurrence /
colour-staple tier, which must still return suggestions.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import store as store_mod  # noqa: E402
from app.main import app  # noqa: E402
from app.store import EDHREC_SIGNAL_ENV, Store, edhrec_signal_enabled, get_store  # noqa: E402
from app.suggest import recommend  # noqa: E402

client = TestClient(app)
store = get_store()

EDHREC_SIGNALS = {"edhrec", "edhrec_inclusion"}


# ---- pure: flag parsing ----------------------------------------------------

def test_default_is_on(monkeypatch):
    monkeypatch.delenv(EDHREC_SIGNAL_ENV, raising=False)
    assert edhrec_signal_enabled() is True


@pytest.mark.parametrize("value", ["off", "OFF", " off ", "0", "false", "no", "disabled"])
def test_off_values(monkeypatch, value):
    monkeypatch.setenv(EDHREC_SIGNAL_ENV, value)
    assert edhrec_signal_enabled() is False


@pytest.mark.parametrize("value", ["on", "ON", "1", "true", "", "of", "typo"])
def test_on_and_unrecognised_values_keep_prod_behaviour(monkeypatch, value):
    monkeypatch.setenv(EDHREC_SIGNAL_ENV, value)
    assert edhrec_signal_enabled() is True


# ---- pure: Store methods without a database --------------------------------

def _bare_store() -> Store:
    s = Store.__new__(Store)  # skip __init__ (no DB, no card file)
    s._edhrec = {"cmd": {"card": (0.4, 0.6)}}
    s._name_to_id = {"krenko": "cmd", "goblin": "card"}
    return s


def test_edhrec_for_both_modes(monkeypatch):
    s = _bare_store()
    monkeypatch.setenv(EDHREC_SIGNAL_ENV, "on")
    assert s.edhrec_for("cmd") == {"card": (0.4, 0.6)}
    monkeypatch.setenv(EDHREC_SIGNAL_ENV, "off")
    assert s.edhrec_for("cmd") == {}
    assert s.edhrec_for("unknown") == {}


def test_load_skips_edhrec_table_when_off(monkeypatch):
    s = _bare_store()
    monkeypatch.setenv(EDHREC_SIGNAL_ENV, "off")

    def _no_query(*_a, **_k):
        raise AssertionError("edhrec_metrics must not be read when the switch is off")
    monkeypatch.setattr(store_mod.db, "query", _no_query)
    s._load_edhrec()
    assert s._edhrec == {}


def test_load_reads_edhrec_table_when_on(monkeypatch):
    s = _bare_store()
    monkeypatch.setenv(EDHREC_SIGNAL_ENV, "on")
    monkeypatch.setattr(store_mod.db, "query",
                        lambda *_a, **_k: [("Krenko", "Goblin", 0.2, 0.9)])
    s._load_edhrec()
    assert s._edhrec == {"cmd": {"card": (0.2, 0.9)}}


# ---- integration: the real store + suggester ---------------------------------

def _edhrec_commander() -> str:
    cmd = next((cid for cid in store._edhrec if store.get(cid)), None)
    if cmd is None:
        pytest.skip("test DB has no edhrec_metrics rows")
    return cmd


def _signals(body: dict) -> set[str]:
    return {r["signal"] for s in body["suggestions"] for r in s["reasons"]}


def _post(cmd: str, deck: list[str]) -> dict:
    r = client.post("/deck/recommend?limit=12&explain=true",
                    json={"commander_id": cmd, "cards": [{"id": c} for c in deck]})
    assert r.status_code == 200
    return r.json()


def test_switch_on_keeps_edhrec_tier(monkeypatch):
    monkeypatch.setenv(EDHREC_SIGNAL_ENV, "on")
    cmd = _edhrec_commander()
    body = _post(cmd, [])
    assert body["tier"] == "edhrec"
    assert body["suggestions"]
    assert _signals(body) & EDHREC_SIGNALS


def test_switch_off_degrades_to_cold_start_and_still_suggests(monkeypatch):
    cmd = _edhrec_commander()
    deck = list(store._edhrec[cmd])[:5]
    monkeypatch.setenv(EDHREC_SIGNAL_ENV, "off")
    assert store.edhrec_for(cmd) == {}
    for d in ([], deck):
        body = _post(cmd, d)
        assert body["tier"] in ("cooccurrence", "color_staple")
        assert len(body["suggestions"]) > 0
        assert not (_signals(body) & EDHREC_SIGNALS), "no EDHREC reason may be emitted when off"
        for s in body["suggestions"]:
            assert "EDHREC" not in " ".join(r["detail"] for r in s["reasons"])


def test_switch_off_direct_recommend_matches_api(monkeypatch):
    cmd = _edhrec_commander()
    monkeypatch.setenv(EDHREC_SIGNAL_ENV, "off")
    out = recommend(store, cmd, [], limit=12, explain=True)
    assert out["tier"] in ("cooccurrence", "color_staple")
    assert out["suggestions"]
