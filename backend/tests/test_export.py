"""Tests for export.py pure formatters + POST /deck/export route.

Covers:
- to_text: zone ordering, Commander: prefix, // zone headers
- to_moxfield_csv: correct header + one row per distinct card
- to_archidekt_csv: correct header + Category populated
- to_manapool: each line matches ``^\d+ .+$``
- POST /deck/export?format=text|moxfield|archidekt|manapool
- POST /deck/export?format=bad  → 400
- Text format export shape is identical to GET /decks/{id}/export
"""

from __future__ import annotations

import csv
import io
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jwt
import pytest
from fastapi.testclient import TestClient

from app import config, decks as decks_module, db
from app.export import (
    ExportRow,
    to_archidekt_csv,
    to_manapool,
    to_moxfield_csv,
    to_text,
)
from app.main import app
from app.store import get_store

client = TestClient(app)
store = get_store()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_USER_A = 1


def _token(user_id: int) -> str:
    return jwt.encode(
        {"sub": str(user_id), "admin": False, "exp": int(time.time()) + 3600},
        config.SIMMANDER_JWT_SECRET,
        algorithm=config.SIMMANDER_JWT_ALG,
    )


def _as(user_id: int) -> None:
    client.cookies.set("simmander_session", _token(user_id))


def _id(name: str) -> str:
    cid = store._name_to_id.get(name.lower())
    assert cid, f"card not found: {name!r}"
    return cid


@pytest.fixture(autouse=True)
def userdecks_tmp():
    """Clean userdecks slate per test; authenticated as user A by default."""
    decks_module.get_userdecks.cache_clear()
    decks_module.get_userdecks()  # ensure schema exists
    with db.cursor(commit=True) as cur:
        cur.execute("TRUNCATE deck_cards, decks RESTART IDENTITY CASCADE")
    _as(_USER_A)
    yield
    client.cookies.clear()
    with db.cursor(commit=True) as cur:
        cur.execute("TRUNCATE deck_cards, decks RESTART IDENTITY CASCADE")
    decks_module.get_userdecks.cache_clear()


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

_SAMPLE_ROWS: list[ExportRow] = [
    {"name": "The Ur-Dragon", "zone": "Commanders", "quantity": 1, "commander": True},
    {"name": "Sol Ring",      "zone": "Ramp",        "quantity": 1, "commander": False},
    {"name": "Command Tower", "zone": "Lands",       "quantity": 1, "commander": False},
    {"name": "Counterspell",  "zone": "Counters",    "quantity": 1, "commander": False},
]


# ---------------------------------------------------------------------------
# Pure formatter tests
# ---------------------------------------------------------------------------

class TestToText:
    def test_commander_line(self):
        text = to_text(_SAMPLE_ROWS)
        assert "Commander: The Ur-Dragon" in text

    def test_no_qty_on_commander_line(self):
        text = to_text(_SAMPLE_ROWS)
        # The commander line must not start with a digit
        cmd_line = next(l for l in text.splitlines() if "The Ur-Dragon" in l)
        assert cmd_line.startswith("Commander:")

    def test_zone_headers(self):
        text = to_text(_SAMPLE_ROWS)
        assert "// Lands" in text
        assert "// Ramp" in text

    def test_card_qty_lines(self):
        text = to_text(_SAMPLE_ROWS)
        assert "1 Sol Ring" in text
        assert "1 Command Tower" in text

    def test_commander_before_lands(self):
        text = to_text(_SAMPLE_ROWS)
        cmd_idx = text.index("Commander:")
        lands_idx = text.index("// Lands")
        assert cmd_idx < lands_idx

    def test_multi_basic_lands(self):
        rows: list[ExportRow] = [
            {"name": "Mountain", "zone": "Lands", "quantity": 8, "commander": False},
        ]
        text = to_text(rows)
        assert "8 Mountain" in text

    def test_unknown_zone_still_exported(self):
        rows: list[ExportRow] = [
            {"name": "Sol Ring", "zone": "Unsorted", "quantity": 1, "commander": False},
        ]
        text = to_text(rows)
        assert "Sol Ring" in text


class TestToMoxfieldCsv:
    def test_header_row(self):
        csv_text = to_moxfield_csv(_SAMPLE_ROWS)
        header = csv_text.splitlines()[0]
        assert header == "Count,Name,Edition,Condition,Language,Foil,Tag"

    def test_row_count(self):
        csv_text = to_moxfield_csv(_SAMPLE_ROWS)
        rows = list(csv.reader(io.StringIO(csv_text)))
        # 1 header + 4 cards
        assert len(rows) == 1 + len(_SAMPLE_ROWS)

    def test_count_and_name_populated(self):
        csv_text = to_moxfield_csv(_SAMPLE_ROWS)
        rows = list(csv.reader(io.StringIO(csv_text)))
        data_rows = rows[1:]
        for row in data_rows:
            count, name = row[0], row[1]
            assert count.isdigit()
            assert len(name) > 0

    def test_optional_cols_blank(self):
        csv_text = to_moxfield_csv(_SAMPLE_ROWS)
        rows = list(csv.reader(io.StringIO(csv_text)))
        # Edition, Condition, Language, Foil, Tag must be blank
        for row in rows[1:]:
            assert row[2] == ""   # Edition
            assert row[3] == ""   # Condition
            assert row[4] == ""   # Language
            assert row[5] == ""   # Foil
            assert row[6] == ""   # Tag

    def test_one_row_per_distinct_card(self):
        csv_text = to_moxfield_csv(_SAMPLE_ROWS)
        rows = list(csv.reader(io.StringIO(csv_text)))
        names = [r[1] for r in rows[1:]]
        assert len(names) == len(set(names))


class TestToArchidektCsv:
    def test_header_row(self):
        csv_text = to_archidekt_csv(_SAMPLE_ROWS)
        header = csv_text.splitlines()[0]
        assert header == "Quantity,Name,Finish,Condition,Edition Code,Collector Number,Category"

    def test_row_count(self):
        csv_text = to_archidekt_csv(_SAMPLE_ROWS)
        rows = list(csv.reader(io.StringIO(csv_text)))
        assert len(rows) == 1 + len(_SAMPLE_ROWS)

    def test_commander_category(self):
        csv_text = to_archidekt_csv(_SAMPLE_ROWS)
        rows = list(csv.reader(io.StringIO(csv_text)))
        cmd_row = next(r for r in rows[1:] if r[1] == "The Ur-Dragon")
        assert cmd_row[6] == "Commander"

    def test_zone_category(self):
        csv_text = to_archidekt_csv(_SAMPLE_ROWS)
        rows = list(csv.reader(io.StringIO(csv_text)))
        sr_row = next(r for r in rows[1:] if r[1] == "Sol Ring")
        assert sr_row[6] == "Ramp"

    def test_one_row_per_distinct_card(self):
        csv_text = to_archidekt_csv(_SAMPLE_ROWS)
        rows = list(csv.reader(io.StringIO(csv_text)))
        names = [r[1] for r in rows[1:]]
        assert len(names) == len(set(names))


class TestToManapool:
    def test_each_line_matches_pattern(self):
        text = to_manapool(_SAMPLE_ROWS)
        pattern = re.compile(r"^\d+ .+$")
        for line in text.strip().splitlines():
            assert pattern.match(line), f"Line doesn't match pattern: {line!r}"

    def test_commander_included(self):
        text = to_manapool(_SAMPLE_ROWS)
        assert "1 The Ur-Dragon" in text

    def test_correct_line_count(self):
        text = to_manapool(_SAMPLE_ROWS)
        assert len(text.strip().splitlines()) == len(_SAMPLE_ROWS)


# ---------------------------------------------------------------------------
# POST /deck/export route tests
# ---------------------------------------------------------------------------

def _deck_request(formats_test: bool = False) -> dict:
    """Build a minimal DeckRequest body using real card ids from the store."""
    ur = _id("The Ur-Dragon")
    sr = _id("Sol Ring")
    ct = _id("Command Tower")
    return {
        "commander_id": ur,
        "cards": [
            {"id": ur, "zone": "Commanders", "quantity": 1},
            {"id": sr, "zone": "Ramp", "quantity": 1},
            {"id": ct, "zone": "Lands", "quantity": 1},
        ],
    }


class TestPostExportRoute:
    def test_text_format(self):
        r = client.post("/deck/export?format=text", json=_deck_request())
        assert r.status_code == 200
        assert "Commander: The Ur-Dragon" in r.text
        assert "1 Sol Ring" in r.text

    def test_moxfield_format(self):
        r = client.post("/deck/export?format=moxfield", json=_deck_request())
        assert r.status_code == 200
        assert r.text.startswith("Count,Name,")

    def test_archidekt_format(self):
        r = client.post("/deck/export?format=archidekt", json=_deck_request())
        assert r.status_code == 200
        assert r.text.startswith("Quantity,Name,")

    def test_manapool_format(self):
        r = client.post("/deck/export?format=manapool", json=_deck_request())
        assert r.status_code == 200
        pattern = re.compile(r"^\d+ .+$")
        for line in r.text.strip().splitlines():
            assert pattern.match(line), f"Bad line: {line!r}"

    def test_unknown_format_400(self):
        r = client.post("/deck/export?format=bogus", json=_deck_request())
        assert r.status_code == 400

    def test_no_auth_required(self):
        """The POST export route must work without a session cookie."""
        client.cookies.clear()
        r = client.post("/deck/export?format=text", json=_deck_request())
        assert r.status_code == 200
        # Restore for fixture cleanup
        _as(_USER_A)

    def test_text_shape_matches_saved_deck_export(self):
        """POST /deck/export?format=text should produce the same text as
        GET /decks/{id}/export for an equivalent saved deck."""
        body = _deck_request()
        deck_id = client.post("/decks", json={**body, "name": "RT"}).json()["id"]

        post_text = client.post("/deck/export?format=text", json=body).text
        get_text = client.get(f"/decks/{deck_id}/export").text

        # Same lines, potentially different trailing whitespace — normalise
        assert post_text.strip() == get_text.strip()


class TestTextRoundTrip:
    def test_text_export_reimport_zero_unresolved(self):
        """Text exported via POST /deck/export can be imported back cleanly."""
        body = _deck_request()
        text = client.post("/deck/export?format=text", json=body).text

        # /decks/import requires a session — _as(_USER_A) is set by fixture
        reimp = client.post("/decks/import", json={"text": text, "name": "RT"}).json()
        assert reimp["unresolved"] == []
        imported_ids = {c["card"]["id"] for c in reimp["deck"]["cards"]}
        original_ids = {e["id"] for e in body["cards"]}
        assert original_ids == imported_ids
