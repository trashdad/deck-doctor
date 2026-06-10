"""Resumable decklist-corpus harness for the SP3 co-occurrence pipeline.

This is the *acquisition* layer. It does ONE thing: fetch raw decklists from
public sources and append them to the corpus as dumb JSON-lines. It computes
NO statistics — lift / synergy / anything numeric is the job of
`scoring/cooccurrence/` (deterministic, tested), never of this script and never
of the LLM driving it.

Corpus contract (see docs/superpowers/specs/2026-06-09-decklist-cooccurrence-design.md §3):

  Deck record:
    {"kind": "deck", "deck_id": "<source>:<nativeid>", "source": "...",
     "commander": "<name|null>", "card_names": ["...", ...]}

  EDHREC aggregate record:
    {"kind": "edhrec", "commander": "<name>",
     "cards": [{"name": "...", "synergy": <float>, "inclusion": <float>}, ...]}

Output: append-only to data/decklists/<source>-<batch>.jsonl. Dedup by deck_id
via data/decklists/.seen_deck_ids (one id per line). Re-running is safe: already
-seen decks are skipped, so the corpus only grows.

Usage:
    python tools/scrape_decklists/runner.py archidekt --ids 23059828,12345678
    python tools/scrape_decklists/runner.py archidekt --id 23059828 --batch hand
    # moxfield / edhrec sources: see _fetch_moxfield / _fetch_edhrec (driven by the
    # delegated LLM, which fills in the site-specific request/parse per PROMPT.md).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = ROOT / "data" / "decklists"
SEEN_FILE = CORPUS_DIR / ".seen_deck_ids"

# Politeness: public APIs, identify ourselves, throttle. EDHREC is the strictest
# (>=2s/req per simmander/sim/edhrec_fetcher.py); keep a floor for all sources.
_UA = "Simmander-SP3/0.1 (research; co-occurrence mining)"
_RATE_S = 2.0
_last_req = 0.0


def _throttle() -> None:
    global _last_req
    dt = time.monotonic() - _last_req
    if dt < _RATE_S:
        time.sleep(_RATE_S - dt)
    _last_req = time.monotonic()


def _get_json(url: str, timeout: int = 60) -> dict:
    _throttle()
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


# ── Corpus writer (append-only, deduped) ─────────────────────────────────────

class Corpus:
    def __init__(self, batch: str = "auto"):
        CORPUS_DIR.mkdir(parents=True, exist_ok=True)
        self._seen: set[str] = set()
        if SEEN_FILE.exists():
            self._seen = {ln.strip() for ln in SEEN_FILE.read_text(encoding="utf-8").splitlines() if ln.strip()}
        self.batch = batch
        self._written = 0
        self._skipped = 0

    def _path(self, source: str) -> Path:
        return CORPUS_DIR / f"{source}-{self.batch}.jsonl"

    def add_deck(self, deck_id: str, source: str, commander: str | None, card_names: list[str]) -> bool:
        if deck_id in self._seen:
            self._skipped += 1
            return False
        if not card_names:
            self._skipped += 1
            return False
        rec = {"kind": "deck", "deck_id": deck_id, "source": source,
               "commander": commander, "card_names": card_names}
        with self._path(source).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self._mark(deck_id)
        self._written += 1
        return True

    def add_edhrec(self, commander: str, cards: list[dict]) -> bool:
        key = f"edhrec:{commander.lower()}"
        if key in self._seen or not cards:
            self._skipped += 1
            return False
        rec = {"kind": "edhrec", "commander": commander, "cards": cards}
        with self._path("edhrec").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self._mark(key)
        self._written += 1
        return True

    def _mark(self, deck_id: str) -> None:
        self._seen.add(deck_id)
        with SEEN_FILE.open("a", encoding="utf-8") as fh:
            fh.write(deck_id + "\n")

    def report(self) -> str:
        return f"wrote {self._written}, skipped {self._skipped} (already-seen/empty)"


# ── Sources ──────────────────────────────────────────────────────────────────

# Archidekt: public JSON API, proven in simmander/scripts/ingest_archidekt_deck.py.
# Excludes any category the deck owner flagged includedInDeck=false (Maybeboard,
# Sideboard, Considering, ...). Returns (commander, qty-expanded-excluded card_names).
_ARCHIDEKT_EXCLUDE = {"Maybeboard", "Sideboard"}


def _fetch_archidekt(native_id: str) -> tuple[str | None, list[str]]:
    data = _get_json(f"https://archidekt.com/api/decks/{native_id}/")
    not_included = {c["name"] for c in data.get("categories", [])
                    if not c.get("includedInDeck", True)} | _ARCHIDEKT_EXCLUDE
    commander: str | None = None
    names: list[str] = []
    for c in data.get("cards", []):
        cats = set(c.get("categories") or [])
        if not_included & cats:
            continue
        name = ((c.get("card", {}) or {}).get("oracleCard", {}) or {}).get("name", "")
        if not name:
            continue
        if "Commander" in cats and commander is None:
            commander = name
        names.append(name)  # unique-card mining wants presence; mining dedups per deck
    return commander, names


def _fetch_moxfield(native_id: str) -> tuple[str | None, list[str]]:
    """Moxfield public deck JSON: https://api2.moxfield.com/v3/decks/all/<id>.

    DELEGATED: the driving LLM implements the request/parse per PROMPT.md —
    pull the mainboard (+ commanders), skip sideboard/maybeboard, return raw
    names. Keep the (commander, names) return shape identical to Archidekt.
    """
    raise NotImplementedError("moxfield fetch is driven by the delegated scraper; see PROMPT.md")


def _fetch_edhrec(commander_slug: str) -> list[dict]:
    """EDHREC commander page → [{name, synergy, inclusion}]. DELEGATED.

    Reuse simmander/sim/edhrec_fetcher.py's slug + JSON-endpoint approach
    (json.edhrec.com/pages/commanders/<slug>.json). Emit raw synergy/inclusion
    numbers EDHREC already publishes — do NOT recompute them.
    """
    raise NotImplementedError("edhrec fetch is driven by the delegated scraper; see PROMPT.md")


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Append raw decklists to the SP3 corpus.")
    ap.add_argument("source", choices=["archidekt", "moxfield", "edhrec"])
    ap.add_argument("--id", help="single native deck id / commander slug")
    ap.add_argument("--ids", help="comma-separated native ids")
    ap.add_argument("--batch", default="auto", help="batch label for the output filename")
    args = ap.parse_args()

    ids = [args.id] if args.id else []
    if args.ids:
        ids += [x.strip() for x in args.ids.split(",") if x.strip()]
    if not ids:
        ap.error("provide --id or --ids")

    corpus = Corpus(batch=args.batch)
    for nid in ids:
        try:
            if args.source == "archidekt":
                cmdr, names = _fetch_archidekt(nid)
                corpus.add_deck(f"archidekt:{nid}", "archidekt", cmdr, names)
            elif args.source == "moxfield":
                cmdr, names = _fetch_moxfield(nid)
                corpus.add_deck(f"moxfield:{nid}", "moxfield", cmdr, names)
            elif args.source == "edhrec":
                corpus.add_edhrec(nid, _fetch_edhrec(nid))
        except Exception as e:  # noqa: BLE001 — keep going; report at end
            print(f"[skip] {args.source}:{nid}: {e}", file=sys.stderr)
    print(corpus.report(), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
