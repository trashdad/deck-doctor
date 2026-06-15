"""Tests for the IER factor breakdown and the /cards/{id}/ier endpoint."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jwt  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config  # noqa: E402
from app.main import app  # noqa: E402
from app.store import get_store  # noqa: E402
from app.ier import ier_breakdown  # noqa: E402

client = TestClient(app)
store = get_store()


def _token(user_id: int, *, admin: bool = False) -> str:
    return jwt.encode(
        {"sub": str(user_id), "admin": admin, "exp": int(time.time()) + 3600},
        config.SIMMANDER_JWT_SECRET, algorithm=config.SIMMANDER_JWT_ALG,
    )


def _first_card_with_ier() -> tuple[str, dict]:
    """Return (card_id, card_dict) for the first card in the store that has an IER."""
    for cid, card in store._cards.items():
        if card.get("ier") is not None:
            return cid, card
    pytest.skip("No cards with IER scores in store — build the store first.")


# ---------------------------------------------------------------------------
# Unit tests for ier_breakdown()
# ---------------------------------------------------------------------------

def test_breakdown_total_matches_stored_ier():
    """The breakdown total must equal the stored card.ier (within float rounding)."""
    cid, card = _first_card_with_ier()
    result = ier_breakdown(card)
    stored = card["ier"]
    assert abs(result["total"] - stored) < 0.05, (
        f"Breakdown total {result['total']} != stored IER {stored} for {card['name']!r}"
    )


def test_breakdown_always_has_base_and_mana_efficiency():
    """Base and mana efficiency factors must always be present."""
    cid, card = _first_card_with_ier()
    result = ier_breakdown(card)
    labels = [f["label"] for f in result["factors"]]
    assert "Base" in labels
    assert "Mana efficiency" in labels


def test_breakdown_base_is_six():
    cid, card = _first_card_with_ier()
    result = ier_breakdown(card)
    base = next(f for f in result["factors"] if f["label"] == "Base")
    assert base["value"] == 6.0


def test_breakdown_total_clamped_to_1_20():
    # Craft a degenerate card that would exceed 20.
    fake = {
        "cmc": 0, "oracle_text": "draw a card", "type_line": "creature",
        "power": "100", "toughness": "100",
        "mechanic_tags": ["card_draw", "ramp", "removal", "board_wipe"],
        "ier": None,
    }
    result = ier_breakdown(fake)
    assert result["total"] <= 20.0
    assert result["total"] >= 1.0


def test_breakdown_conditional_factor_appears():
    fake = {
        "cmc": 2, "oracle_text": "unless you pay 2 life, draw a card.",
        "type_line": "instant", "power": None, "toughness": None,
        "mechanic_tags": ["card_draw"], "ier": None,
    }
    result = ier_breakdown(fake)
    labels = [f["label"] for f in result["factors"]]
    assert "Conditional effect" in labels
    cond = next(f for f in result["factors"] if f["label"] == "Conditional effect")
    assert cond["value"] == -1.0


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------

def test_endpoint_anonymous_returns_locked():
    """Anonymous requests must get locked=True and NO factors."""
    cid, _ = _first_card_with_ier()
    r = client.get(f"/cards/{cid}/ier")
    assert r.status_code == 200
    body = r.json()
    assert body["locked"] is True
    assert "factors" not in body
    assert "ier" in body


def test_endpoint_admin_returns_factors():
    """Admin tokens (Mythic tier) must get locked=False and the factors list."""
    cid, card = _first_card_with_ier()
    token = _token(99, admin=True)
    r = client.get(f"/cards/{cid}/ier",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["locked"] is False
    assert "factors" in body
    assert len(body["factors"]) >= 2  # at minimum Base + Mana efficiency


def test_endpoint_non_admin_user_is_locked():
    """A regular (non-admin) logged-in user must still get locked=True."""
    cid, _ = _first_card_with_ier()
    token = _token(42, admin=False)
    r = client.get(f"/cards/{cid}/ier",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["locked"] is True


def test_endpoint_unknown_card_404():
    r = client.get("/cards/totally-unknown-card-id-xyz/ier")
    assert r.status_code == 404
