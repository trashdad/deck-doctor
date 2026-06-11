"""SP6 deck persistence + import/export tests."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jwt  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config, db, decks as decks_module  # noqa: E402
from app.main import app  # noqa: E402
from app.store import get_store  # noqa: E402

client = TestClient(app)
store = get_store()

_USER_A = 1
_USER_B = 2


def _token(user_id: int) -> str:
    return jwt.encode(
        {"sub": str(user_id), "admin": False, "exp": int(time.time()) + 3600},
        config.SIMMANDER_JWT_SECRET, algorithm=config.SIMMANDER_JWT_ALG)


def _as(user_id: int) -> None:
    client.cookies.set("simmander_session", _token(user_id))


@pytest.fixture(autouse=True)
def userdecks_tmp():
    """Clean userdecks slate per test; authenticated as user A by default."""
    decks_module.get_userdecks.cache_clear()
    decks_module.get_userdecks()            # ensure the schema exists
    with db.cursor(commit=True) as cur:
        cur.execute("TRUNCATE deck_cards, decks RESTART IDENTITY CASCADE")
    _as(_USER_A)
    yield
    client.cookies.clear()
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
    again = decks_module.get_userdecks().get(deck_id, _USER_A)
    assert again is not None and again["name"] == "P"


def test_decks_require_login():
    client.cookies.clear()
    assert client.get("/decks").status_code == 401
    assert client.post("/decks", json={"name": "x", "cards": []}).status_code == 401
    _as(_USER_A)  # restore for any later assertions in this test


def test_user_cannot_see_or_touch_another_users_deck():
    made = client.post("/decks", json={"name": "A's deck", "cards": []}).json()
    deck_id = made["id"]
    _as(_USER_B)
    assert client.get("/decks").json() == []                 # B sees nothing
    assert client.get(f"/decks/{deck_id}").status_code == 404  # B can't read A's
    assert client.put(f"/decks/{deck_id}",
                      json={"name": "hijacked", "cards": []}).status_code == 404  # B can't update A's
    assert client.delete(f"/decks/{deck_id}").status_code == 404  # B can't delete A's
    _as(_USER_A)
    assert any(d["id"] == deck_id for d in client.get("/decks").json())  # A still has it


def test_auth_me_shapes():
    me = client.get("/auth/me").json()
    assert me["user"]["id"] == _USER_A
    client.cookies.clear()
    assert client.get("/auth/me").json() == {"user": None}
    _as(_USER_A)
