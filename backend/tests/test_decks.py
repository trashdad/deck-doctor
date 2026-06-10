"""SP6 deck persistence + import/export tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import db, decks as decks_module  # noqa: E402
from app.main import app  # noqa: E402
from app.store import get_store  # noqa: E402

client = TestClient(app)
store = get_store()


@pytest.fixture(autouse=True)
def userdecks_tmp():
    """Clean userdecks (Postgres) slate per test; clear the lru_cache around each."""
    decks_module.get_userdecks.cache_clear()
    decks_module.get_userdecks()            # ensure the schema exists
    with db.cursor(commit=True) as cur:
        cur.execute("TRUNCATE deck_cards, decks RESTART IDENTITY CASCADE")
    yield
    with db.cursor(commit=True) as cur:
        cur.execute("TRUNCATE deck_cards, decks RESTART IDENTITY CASCADE")
    decks_module.get_userdecks.cache_clear()


def _id(name: str) -> str:
    cid = store._name_to_id.get(name.lower())
    assert cid, f"card not found: {name!r}"
    return cid


def test_crud_roundtrip():
    sr, ct, ur = _id("Sol Ring"), _id("Command Tower"), _id("The Ur-Dragon")
    body = {"name": "My Deck", "commander_id": ur,
            "cards": [{"id": ur, "zone": "Commanders", "quantity": 1},
                      {"id": sr, "zone": "Ramp", "quantity": 1},
                      {"id": ct, "zone": "Lands", "quantity": 1}]}
    created = client.post("/decks", json=body)
    assert created.status_code == 201
    deck_id = created.json()["id"]

    listed = client.get("/decks").json()
    assert any(d["id"] == deck_id and d["card_count"] == 3 for d in listed)

    detail = client.get(f"/decks/{deck_id}").json()
    assert len(detail["cards"]) == 3
    assert {c["card"]["id"] for c in detail["cards"]} == {sr, ct, ur}
    assert all("name" in c["card"] for c in detail["cards"])

    lb = _id("Lightning Bolt")
    body["cards"].append({"id": lb, "zone": "Removal", "quantity": 1})
    upd = client.put(f"/decks/{deck_id}", json=body)
    assert upd.status_code == 200
    assert len(upd.json()["cards"]) == 4

    assert client.delete(f"/decks/{deck_id}").status_code == 204
    assert client.get(f"/decks/{deck_id}").status_code == 404


def test_import_formats():
    text = """
Commander: The Ur-Dragon
1 Sol Ring
1x Command Tower
Lightning Bolt
1 Sol Ring (C21) 263 *F*
## Lands
SB: 1 Swords to Plowshares
1 Totally Fake Card
"""
    r = client.post("/decks/import", json={"text": text, "name": "Imp"})
    assert r.status_code == 200
    body = r.json()
    names = {c["card"]["name"] for c in body["deck"]["cards"]}
    assert "The Ur-Dragon" in names
    assert "Sol Ring" in names and "Command Tower" in names and "Lightning Bolt" in names
    assert "Swords to Plowshares" not in names           # sideboard excluded
    assert body["deck"]["commander_id"] == _id("The Ur-Dragon")
    assert body["unresolved"] == ["1 Totally Fake Card"]
    # Sol Ring deduped (appeared twice) → single entry
    assert sum(1 for c in body["deck"]["cards"] if c["card"]["name"] == "Sol Ring") == 1


def test_import_basics_quantity():
    text = "8 Mountain\n3 Sol Ring\n"
    body = client.post("/decks/import", json={"text": text}).json()["deck"]
    qty = {c["card"]["name"]: c["quantity"] for c in body["cards"]}
    assert qty["Mountain"] == 8
    assert qty["Sol Ring"] == 1            # singleton clamp


def test_export_roundtrip():
    ur, sr, mt = _id("The Ur-Dragon"), _id("Sol Ring"), _id("Mountain")
    body = {"name": "RT", "commander_id": ur,
            "cards": [{"id": ur, "zone": "Commanders", "quantity": 1},
                      {"id": sr, "zone": "Ramp", "quantity": 1},
                      {"id": mt, "zone": "Lands", "quantity": 8}]}
    deck_id = client.post("/decks", json=body).json()["id"]
    text = client.get(f"/decks/{deck_id}/export").text

    reimp = client.post("/decks/import", json={"text": text}).json()
    assert reimp["unresolved"] == []
    assert reimp["deck"]["commander_id"] == ur
    orig = {(c["id"], c["quantity"]) for c in body["cards"]}
    got = {(c["card"]["id"], c["quantity"]) for c in reimp["deck"]["cards"]}
    assert orig == got


def test_persistence_across_instances():
    ur = _id("The Ur-Dragon")
    deck_id = client.post(
        "/decks", json={"name": "P", "commander_id": ur,
                        "cards": [{"id": ur, "zone": "Commanders", "quantity": 1}]},
    ).json()["id"]
    decks_module.get_userdecks.cache_clear()      # drop the in-memory instance
    again = decks_module.get_userdecks().get(deck_id)
    assert again is not None and again["name"] == "P"
