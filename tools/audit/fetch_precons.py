"""Fetch Commander precon decklists and write data/precons/precons.json.

Sources (public, no auth):
  * Scryfall  https://api.scryfall.com/sets   -> which sets are set_type == "commander"
    (Scryfall has no decklist endpoint; a set's card pool covers every deck in the
    product plus reprints, so it cannot give exact 100-card lists.)
  * MTGJSON   https://mtgjson.com/api/v5/DeckList.json and
              https://mtgjson.com/api/v5/decks/<fileName>.json
    MTGJSON's "Commander Deck" entries are exact lists transcribed from the WotC
    decklist articles (each entry carries its `source` URL).

Polite: >= 100 ms between requests, explicit User-Agent / Accept headers.

Usage: python -I tools/audit/fetch_precons.py [--out data/precons/precons.json]
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
UA = "SimmanderDeckDoctor/0.1 (precon audit; +https://simmander.app/deck-doctor)"
HEADERS = {"User-Agent": UA, "Accept": "application/json"}
DELAY = 0.12


def get(url: str) -> dict:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    time.sleep(DELAY)
    return data


def front_name(card: dict) -> str:
    # Match the decks.sqlite convention: card_name stores the front face name
    # for DFCs ("Name // Back" -> "Name").
    return card.get("faceName") or card["name"].split(" // ")[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(REPO / "data" / "precons" / "precons.json"))
    a = ap.parse_args()

    sets = get("https://api.scryfall.com/sets")["data"]
    cmd_sets = {s["code"].upper(): s for s in sets if s["set_type"] == "commander"}

    index = get("https://mtgjson.com/api/v5/DeckList.json")
    meta = index["meta"]
    entries = [e for e in index["data"] if e["type"] in ("Commander Deck", "MTGO Commander Deck")]
    print(f"mtgjson {meta}; commander deck entries: {len(entries)}")

    out: dict[str, dict] = {}
    skipped = 0
    for e in entries:
        url = f"https://mtgjson.com/api/v5/decks/{e['fileName']}.json"
        try:
            d = get(url)["data"]
        except Exception as ex:  # noqa: BLE001
            print(f"  FAIL {e['fileName']}: {ex}")
            skipped += 1
            continue
        commanders = [front_name(c) for c in d.get("commander", [])]
        cards: list[str] = []
        for c in d.get("mainBoard", []):
            n = front_name(c)
            if n not in cards:
                cards.append(n)
        key = f"{e['name']} [{e['code']}]"
        out[key] = {
            "commander": commanders[0] if commanders else None,
            "commanders": commanders,
            "set_code": e["code"],
            "set_is_scryfall_commander_type": e["code"].upper() in cmd_sets,
            "release_date": e["releaseDate"],
            "mtgjson_file": e["fileName"],
            "wotc_source": e.get("source"),
            "n_mainboard_entries": sum(c.get("count", 1) for c in d.get("mainBoard", [])),
            "cards": cards,
        }
        print(f"  {key}: cmd={commanders} cards={len(cards)}")

    doc = {
        "_meta": {
            "fetched": date.today().isoformat(),
            "sources": [
                "https://api.scryfall.com/sets (set_type == commander)",
                "https://mtgjson.com/api/v5/DeckList.json",
                "https://mtgjson.com/api/v5/decks/<fileName>.json",
            ],
            "mtgjson_version": meta.get("version"),
            "mtgjson_date": meta.get("date"),
            "scryfall_commander_sets": len(cmd_sets),
            "decks": len(out),
            "failed": skipped,
            "note": "cards = distinct mainboard card names (front face), commander excluded; "
                    "MTGJSON lists are transcribed from the WotC decklist articles in wotc_source.",
        },
        **out,
    }
    p = Path(a.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {p} decks={len(out)} failed={skipped}")


if __name__ == "__main__":
    main()
