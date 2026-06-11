"""Enrich land cards with prices + produced_mana from Scryfall.

Reads data/cards.json, selects every card whose type_line contains "Land",
batches their ids to the Scryfall collection endpoint (max 75 per request),
and writes backend/data/land_meta.json mapping:

    id -> {"name": ..., "produced_mana": ["W", ...], "usd": <float|null>}

Run from repo root or the backend/ directory:
    python backend/scripts/enrich_lands.py
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

BATCH_SIZE = 75
SLEEP_MS = 150  # ms between Scryfall requests (well under their 10req/s limit)
SCRYFALL_COLLECTION_URL = "https://api.scryfall.com/cards/collection"

# Resolve paths relative to the repo root regardless of cwd.
_SCRIPT_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _SCRIPT_DIR.parent
_REPO_ROOT = _BACKEND_DIR.parent
CARDS_PATH = _REPO_ROOT / "data" / "cards.json"
OUT_PATH = _BACKEND_DIR / "data" / "land_meta.json"


def scryfall_collection(identifiers: list[dict]) -> list[dict]:
    """POST to /cards/collection; return the `data` list from the response."""
    payload = json.dumps({"identifiers": identifiers}).encode()
    req = urllib.request.Request(
        SCRYFALL_COLLECTION_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "simmander-deckbuilder/enrich-lands (+https://github.com/trashdad/simmander)",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read())
    return body.get("data", [])


def extract_meta(card: dict) -> dict:
    """Extract the fields we care about from a Scryfall card object."""
    # produced_mana may be on the top-level card or on card_faces[0]
    produced_mana = card.get("produced_mana")
    if not produced_mana:
        for face in card.get("card_faces") or []:
            if face.get("produced_mana"):
                produced_mana = face["produced_mana"]
                break

    prices = card.get("prices") or {}
    usd: float | None = None
    raw_usd = prices.get("usd")
    if raw_usd is not None:
        try:
            usd = float(raw_usd)
        except (TypeError, ValueError):
            pass
    if usd is None:
        raw_foil = prices.get("usd_foil")
        if raw_foil is not None:
            try:
                usd = float(raw_foil)
            except (TypeError, ValueError):
                pass

    return {
        "name": card.get("name", ""),
        "produced_mana": produced_mana or [],
        "usd": usd,
    }


def main() -> None:
    print(f"Loading {CARDS_PATH} …", flush=True)
    with CARDS_PATH.open(encoding="utf-8") as fh:
        raw = json.load(fh)
    cards = raw["data"] if isinstance(raw, dict) and "data" in raw else raw

    lands = [c for c in cards if "Land" in (c.get("type_line") or "")]
    print(f"Found {len(lands)} land cards.", flush=True)

    land_ids = [c["id"] for c in lands]
    batches = [land_ids[i:i + BATCH_SIZE] for i in range(0, len(land_ids), BATCH_SIZE)]
    print(f"Batching into {len(batches)} requests of <={BATCH_SIZE} ids each.", flush=True)

    meta: dict[str, dict] = {}
    errors = 0

    for i, batch in enumerate(batches):
        identifiers = [{"id": cid} for cid in batch]
        try:
            results = scryfall_collection(identifiers)
            for card in results:
                cid = card.get("id")
                if cid:
                    meta[cid] = extract_meta(card)
            print(
                f"  Batch {i + 1}/{len(batches)}: got {len(results)} cards "
                f"(total so far: {len(meta)})",
                flush=True,
            )
        except Exception as exc:
            errors += 1
            print(f"  Batch {i + 1}/{len(batches)} FAILED: {exc}", file=sys.stderr, flush=True)

        # Respect Scryfall rate limits
        if i < len(batches) - 1:
            time.sleep(SLEEP_MS / 1000.0)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2)

    # Summary stats
    with_price = sum(1 for v in meta.values() if v["usd"] is not None)
    without_price = len(meta) - with_price
    print(f"\nDone. Wrote {len(meta)} entries to {OUT_PATH}")
    print(f"  with usd price:    {with_price}")
    print(f"  null price:        {without_price}")
    if errors:
        print(f"  batches with errors: {errors}", file=sys.stderr)

    # Spot-check a few staples
    name_to_id = {v["name"].lower(): k for k, v in meta.items()}
    for staple in ["Command Tower", "Breeding Pool", "Sunpetal Grove", "Sol Ring"]:
        cid = name_to_id.get(staple.lower())
        if cid:
            m = meta[cid]
            print(f"  check {staple}: produced_mana={m['produced_mana']}, usd={m['usd']}")
        else:
            print(f"  check {staple}: NOT FOUND in output (it may not be a land)")


if __name__ == "__main__":
    main()
