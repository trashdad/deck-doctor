"""Tests for the fill_lands manabase optimizer (SP12)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.doctor import TEMPLATE, category_of  # noqa: E402
from app.manabase import fill_lands  # noqa: E402
from app.store import get_store  # noqa: E402

store = get_store()


def _id(name: str) -> str:
    cid = store._name_to_id.get(name.lower())
    assert cid, f"card not found: {name!r}"
    return cid


def _nonland_cards(color_identity: set[str], n: int) -> list[str]:
    """Return n nonland card ids whose color identity fits `color_identity`."""
    out = []
    for cid, card in store._cards.items():
        tl = card.get("type_line") or ""
        if "Land" in tl:
            continue
        if not set(card.get("color_identity") or []) <= color_identity:
            continue
        out.append(cid)
        if len(out) >= n:
            break
    return out


def _land_cards(color_identity: set[str], n: int) -> list[str]:
    """Return n land card ids whose color identity fits `color_identity`."""
    out = []
    for cid, card in store._cards.items():
        tl = card.get("type_line") or ""
        if "Land" not in tl:
            continue
        if not set(card.get("color_identity") or []) <= color_identity:
            continue
        out.append(cid)
        if len(out) >= n:
            break
    return out


# -------------------------------------------------------------------------
# Test 1: fill-only — deck already at land target returns []
# -------------------------------------------------------------------------
def test_fill_only_no_deficit():
    """A deck with >= template_land lands should get no additions."""
    # Use a 5-color commander (Ur-Dragon) so any land can be in the deck
    cmd_id = _id("The Ur-Dragon")
    ci = {"W", "U", "B", "R", "G"}
    template = {**TEMPLATE, "land": 37}
    # Give the deck exactly 37 lands
    lands = _land_cards(ci, 37)
    result = fill_lands(store, cmd_id, lands, template=template)
    assert result == [], f"Expected no additions but got {len(result)} cards"


# -------------------------------------------------------------------------
# Test 2: mono-color deck gets only on-color basics + on-color nonbasics
# -------------------------------------------------------------------------
def test_mono_color_only_on_color():
    """Fill a mono-white deck from scratch — all added lands must be mono-W compatible."""
    # Find a true mono-white (CI == {"W"}) legendary creature
    mono_w_cmd = next(
        (cid for cid, card in store._cards.items()
         if "Legendary" in (card.get("type_line") or "")
         and "Creature" in (card.get("type_line") or "")
         and set(card.get("color_identity") or []) == {"W"}),
        None,
    )
    assert mono_w_cmd, "No mono-white legendary creature found"

    nonlands = _nonland_cards({"W"}, 10)
    template = {**TEMPLATE, "land": 37}

    result = fill_lands(store, mono_w_cmd, nonlands, template=template)
    assert result, "Should add some lands"
    total_added = sum(a["quantity"] for a in result)
    # 0 current lands + 10 nonlands → deficit = 37 (nonland cards don't count as lands)
    assert total_added == 37, f"Expected 37 lands added (deficit=37), got {total_added}"

    for a in result:
        card = store.get(a["card_id"])
        assert card is not None
        assert "Land" in (card.get("type_line") or ""), f"Non-land added: {card['name']}"
        ci = set(card.get("color_identity") or [])
        assert ci <= {"W"}, f"Off-color land added: {card['name']} (ci={ci})"
        assert a["zone"] == "Lands"


# -------------------------------------------------------------------------
# Test 3: 3-color deck gets multi-color fixers
# -------------------------------------------------------------------------
def test_multicolor_gets_fixers():
    """A GWU deck should get multi-color fixing lands (nonbasics with multiple colors)."""
    # Find a GWU commander
    cmd_id = None
    for cid, card in store._cards.items():
        ci = set(card.get("color_identity") or [])
        tl = card.get("type_line") or ""
        if ci == {"G", "W", "U"} and "Legendary" in tl and "Creature" in tl:
            cmd_id = cid
            break
    assert cmd_id, "No GWU legendary creature found"

    nonlands = _nonland_cards({"G", "W", "U"}, 5)
    template = {**TEMPLATE, "land": 37}

    result = fill_lands(store, cmd_id, nonlands, template=template)
    assert result, "Should add lands"

    # There should be at least one nonbasic (multi-color fixer)
    nonbasics = [a for a in result
                 if "Basic" not in (store.get(a["card_id"]).get("type_line") or "")]
    assert len(nonbasics) > 0, "Expected at least one nonbasic land in 3-color fill"

    # Check no off-CI land was added
    gwu = {"G", "W", "U"}
    for a in result:
        card = store.get(a["card_id"])
        ci = set(card.get("color_identity") or [])
        assert ci <= gwu, f"Off-color land: {card['name']} (ci={ci})"


# -------------------------------------------------------------------------
# Test 4: max_price excludes expensive lands while cheap ones remain
# -------------------------------------------------------------------------
def test_price_cap_excludes_expensive_lands():
    """max_price=10 excludes lands with usd > $10; cheap fixers still included."""
    # Find a commander with enough land_meta coverage (use 5-color to maximize pool)
    cmd_id = _id("The Ur-Dragon")  # 5-color

    nonlands = _nonland_cards({"W", "U", "B", "R", "G"}, 5)
    template = {**TEMPLATE, "land": 37}

    # With no cap: get all staple lands
    result_uncapped = fill_lands(store, cmd_id, nonlands, template=template, max_price=0)

    # With $10 cap
    result_capped = fill_lands(store, cmd_id, nonlands, template=template, max_price=10.0)

    # Check: no land in the capped result has usd > 10
    wubrg = {"W", "U", "B", "R", "G"}
    for a in result_capped:
        meta = store.land_meta.get(a["card_id"])
        if meta and meta.get("usd") is not None:
            assert meta["usd"] <= 10.0, (
                f"Expensive land slipped through: {meta['name']} (${meta['usd']:.2f})"
            )

    # The uncapped result should include at least one land over $10
    # (Breeding Pool, Hallowed Fountain, etc. are > $10 in the data)
    expensive_in_uncapped = [
        a for a in result_uncapped
        if (meta := store.land_meta.get(a["card_id"])) and meta.get("usd") and meta["usd"] > 10
    ]
    # If land_meta has prices, we expect some expensive staples in the uncapped run.
    # Only assert this if land_meta is actually populated.
    if store.land_meta:
        assert len(expensive_in_uncapped) >= 1, (
            "Expected at least one expensive land in uncapped fill "
            f"(Breeding Pool=${store.land_meta.get(store._name_to_id.get('breeding pool', ''), {}).get('usd')})"
        )
        # And the capped result should have fewer nonbasics than uncapped
        # (some expensive lands excluded)
        assert len(result_capped) <= len(result_uncapped)


# -------------------------------------------------------------------------
# Test 5: 400 with no commander
# -------------------------------------------------------------------------
def test_no_commander_raises():
    """fill_lands itself doesn't raise; the 400 is gated in the endpoint.
    Test the endpoint directly via the FastAPI test client."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    resp = client.post("/deck/lands", json={"cards": [], "commander_id": None})
    assert resp.status_code == 400


# -------------------------------------------------------------------------
# Test 6: correct total quantity added
# -------------------------------------------------------------------------
def test_quantity_matches_deficit():
    """Total lands added should equal exactly the deficit."""
    # Use Ur-Dragon (5-color) to use 5-color lands; simpler to find 20 lands
    cmd_id = _id("The Ur-Dragon")
    ci = {"W", "U", "B", "R", "G"}
    # Provide 20 lands already in the deck
    existing_lands = _land_cards(ci, 20)
    template = {**TEMPLATE, "land": 37}

    result = fill_lands(store, cmd_id, existing_lands, template=template)
    total_added = sum(a["quantity"] for a in result)
    assert total_added == 17, f"37-20=17 expected, got {total_added}"
