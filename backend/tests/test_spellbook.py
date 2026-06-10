"""SP7 Commander Spellbook integration tests (fixture DB, no network)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config, store as store_module  # noqa: E402
from app.main import app  # noqa: E402
from app.store import get_store  # noqa: E402
from app.suggest import recommend  # noqa: E402
from tests.fixtures.spellbook_fixture import make_spellbook_db  # noqa: E402

client = TestClient(app)


@pytest.fixture
def fx(tmp_path, monkeypatch):
    """Swap in the fixture spellbook + a fresh Store; restore the real store after."""
    real = get_store()                       # resolve fixture names via the real index
    members = make_spellbook_db(tmp_path / "spellbook.sqlite", real)
    monkeypatch.setattr(config, "SPELLBOOK_PATH", tmp_path / "spellbook.sqlite")
    store_module.get_store.cache_clear()
    yield {"store": get_store(), "members": members}
    store_module.get_store.cache_clear()     # next access rebuilds the real store


def test_load_skips_unresolvable(fx):
    # fxC contains "Nonexistent Card XYZ" → skipped; fxA + fxB load → 2.
    assert len(fx["store"]._spellbook) == 2


def test_deck_combos_complete_and_near(fx):
    a = fx["members"]["a_members"]
    b = fx["members"]["b_members"]
    deck = a + b[:2]                           # all of A + 2 of B (exactly 1 missing)
    res = fx["store"].deck_spellbook(deck)
    complete_ids = {c["combo_id"] for c in res["complete"]}
    near = {n["combo"]["combo_id"]: n["missing"] for n in res["near"]}
    assert "fxA" in complete_ids
    assert "fxB" in near
    assert near["fxB"] == b[2]                  # the one missing B member


def test_suggest_spellbook_completion(fx):
    store = fx["store"]
    a = fx["members"]["a_members"]
    cmd = store._name_to_id["the ur-dragon"]   # WUBRG ⊇ colorless combo A
    res = recommend(store, cmd, [a[0]], limit=80, explain=True)
    by_id = {s["card"]["id"]: s for s in res["suggestions"]}
    assert a[1] in by_id, "missing combo piece not suggested"
    reasons = by_id[a[1]]["reasons"]
    engine = next((r for r in reasons if r["signal"] == "engine"), None)
    assert engine is not None
    assert "Infinite mana" in engine["detail"]
    assert engine["value"] == 1.2              # SPELLBOOK_BONUS > mined engine 1.0


def test_spellbook_endpoint_shapes(fx):
    sr = fx["store"]._name_to_id["sol ring"]   # in fixture combo A
    r = client.get(f"/cards/{sr}/spellbook-combos")
    assert r.status_code == 200
    combos = r.json()
    assert any(c["combo_id"] == "fxA" for c in combos)
    pops = [c["popularity"] for c in combos if c["popularity"] is not None]
    assert pops == sorted(pops, reverse=True)
    for c in combos:
        assert all("name" in m for m in c["members"])
    assert client.get("/cards/not-a-card/spellbook-combos").status_code == 404
