"""Filter the full Scryfall default-cards.json to commander-legal cards.

Reads the 500MB Scryfall bulk dump and writes a slimmed JSON array containing
one English print per oracle_id for every card that is legal (or restricted)
in Commander.  Output is the native format the backend store.py expects.

Usage:
    python scoring/prep_cards.py \
        --src C:/simmander/simmander/data/default-cards.json \
        --out data/cards.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKIP_LAYOUTS = {
    "token", "double_faced_token", "emblem", "art_series",
    "reversible_card", "scheme", "planar", "vanguard",
}

COMMANDER_LEGAL = {"legal", "restricted"}


def _image(card: dict) -> str | None:
    uris = card.get("image_uris") or {}
    return uris.get("normal") or uris.get("large") or uris.get("small")


def _keep(card: dict) -> bool:
    if card.get("lang", "en") != "en":
        return False
    if card.get("layout", "normal") in SKIP_LAYOUTS:
        return False
    # Drop silver-border / acorn / "un-set" joke cards: not real Commander cards
    # and the only meaningful gap in MTGish typed coverage (see fingerprint spec §5.2).
    if card.get("security_stamp") == "acorn":
        return False
    if card.get("border_color") == "silver":
        return False
    if card.get("set_type") == "funny":
        return False
    legality = (card.get("legalities") or {}).get("commander", "not_legal")
    if legality not in COMMANDER_LEGAL:
        return False
    return True


def _slim(card: dict) -> dict:
    """Keep only the fields the deckbuilder backend + frontend need."""
    out: dict = {
        "id": card["id"],
        "oracle_id": card.get("oracle_id", card["id"]),
        "name": card["name"],
        "mana_cost": card.get("mana_cost", ""),
        "cmc": card.get("cmc", 0),
        "type_line": card.get("type_line", ""),
        "oracle_text": card.get("oracle_text", ""),
        "colors": card.get("colors", []),
        "color_identity": card.get("color_identity", []),
        "power": card.get("power"),
        "toughness": card.get("toughness"),
        "loyalty": card.get("loyalty"),
        "keywords": card.get("keywords", []),
        "rarity": card.get("rarity", ""),
        "set": card.get("set", ""),
        "released_at": card.get("released_at", ""),
    }
    img = _image(card)
    if img:
        out["image_uris"] = {"normal": img}
    # include card_faces for DFC so the frontend can show both halves
    if card.get("card_faces"):
        out["card_faces"] = card["card_faces"]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="Path to Scryfall default-cards.json")
    ap.add_argument("--out", required=True, help="Output path for filtered cards.json")
    args = ap.parse_args()

    src = Path(args.src)
    out = Path(args.out)

    if not src.exists():
        sys.exit(f"Source not found: {src}")

    print(f"Loading {src} ({src.stat().st_size // 1_048_576} MB) …", flush=True)
    with src.open(encoding="utf-8") as fh:
        all_cards: list[dict] = json.load(fh)

    print(f"  {len(all_cards):,} total prints — filtering …", flush=True)

    # One print per oracle_id: prefer newest release date, then highest-res image
    by_oracle: dict[str, dict] = {}
    for card in all_cards:
        if not _keep(card):
            continue
        oid = card.get("oracle_id", card["id"])
        existing = by_oracle.get(oid)
        if existing is None:
            by_oracle[oid] = card
        else:
            # prefer newer release; break ties by having a normal image
            if card.get("released_at", "") > existing.get("released_at", ""):
                by_oracle[oid] = card
            elif card.get("released_at", "") == existing.get("released_at", ""):
                if _image(card) and not _image(existing):
                    by_oracle[oid] = card

    slimmed = [_slim(c) for c in by_oracle.values()]
    slimmed.sort(key=lambda c: c["name"])

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        json.dump(slimmed, fh, ensure_ascii=False, separators=(",", ":"))

    size_kb = out.stat().st_size // 1024
    print(f"  Done. {len(slimmed):,} commander-legal cards -> {out} ({size_kb:,} KB)")


if __name__ == "__main__":
    main()
