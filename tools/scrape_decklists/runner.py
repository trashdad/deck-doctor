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
import re
import ssl
import sys
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = ROOT / "data" / "decklists"
SEEN_FILE = CORPUS_DIR / ".seen_deck_ids"

# Politeness: public APIs, identify ourselves, throttle PER HOST so independent
# hosts proceed in parallel. Intervals reflect each host's tolerance: EDHREC's
# json endpoint is CDN-backed (lenient); edhrec.com/api and the deck sites are
# dynamic (more conservative). A worker pool overlaps network latency; the
# per-host limiter keeps us polite regardless of pool size.
_UA = "Simmander-SP3/0.1 (research; co-occurrence mining)"
_HOST_INTERVAL = {
    "json.edhrec.com": 0.3,   # static CDN JSON — tolerant
    "edhrec.com": 0.5,        # deckpreview API — moderate
    "archidekt.com": 0.7,
    "api2.moxfield.com": 1.2,  # Cloudflare-gated — gentle
}
_DEFAULT_INTERVAL = 1.0
_host_lock = threading.Lock()
_host_last: dict[str, float] = {}

try:  # verified TLS where certifi is present (matches sim/edhrec_fetcher.py)
    import certifi as _certifi
    _SSL_CTX = ssl.create_default_context(cafile=_certifi.where())
except ImportError:  # pragma: no cover
    _SSL_CTX = ssl.create_default_context()


def _throttle(host: str) -> None:
    """Block until this host's min-interval has elapsed. Thread-safe: the slot is
    reserved under the lock, so concurrent workers space out per host correctly."""
    interval = _HOST_INTERVAL.get(host, _DEFAULT_INTERVAL)
    while True:
        with _host_lock:
            now = time.monotonic()
            wait = interval - (now - _host_last.get(host, 0.0))
            if wait <= 0:
                _host_last[host] = now
                return
        time.sleep(wait)


def _get_json(url: str, timeout: int = 60, headers: dict | None = None) -> dict:
    _throttle(urllib.parse.urlparse(url).hostname or "")
    hdr = {"User-Agent": _UA}
    if headers:
        hdr.update(headers)
    req = urllib.request.Request(url, headers=hdr)
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as r:
        return json.loads(r.read())


# ── EDHREC slug (mirrors simmander/sim/edhrec_fetcher.commander_to_slug) ───────

def commander_to_slug(name: str) -> str:
    """'Atraxa, Praetors' Voice' -> 'atraxa-praetors-voice'."""
    slug = name.lower().replace("'", "").replace(",", "")
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug)
    return slug.strip("-")


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
    """Moxfield public deck JSON: https://api2.moxfield.com/v3/decks/all/<publicId>.

    Pulls boards.mainboard (+ boards.commanders), skips sideboard / maybeboard /
    other boards. Returns (commander, card_names) in the same shape as Archidekt:
    the commander is included in card_names; names are as printed.

    Each board has shape {"cards": {<id>: {"card": {"name": ...}, "quantity": N}}}.
    We record card *presence* (one name per distinct card) — the downstream
    mining dedups per deck and only cares about which cards co-occur.

    NOTE: api2.moxfield.com sits behind Cloudflare and returns HTTP 403 to
    non-browser clients from many IPs. When that happens this raises and the
    caller logs a skip; the EDHREC deckpreview path (below) recovers most
    Moxfield-originated decklists without touching Moxfield directly.
    """
    data = _get_json(
        f"https://api2.moxfield.com/v3/decks/all/{native_id}",
        headers={"Accept": "application/json"},
    )
    boards = data.get("boards", {}) or {}

    def _board_names(board_key: str) -> list[str]:
        cards = ((boards.get(board_key) or {}).get("cards") or {})
        out: list[str] = []
        for entry in cards.values():
            name = ((entry or {}).get("card") or {}).get("name", "")
            if name:
                out.append(name)
        return out

    commander = None
    cmdr_names = _board_names("commanders")
    if cmdr_names:
        commander = cmdr_names[0]

    # mainboard + commanders only; explicitly ignore sideboard/maybeboard/etc.
    names = cmdr_names + _board_names("mainboard")
    return commander, names


def _edhrec_commander_url(commander: str) -> str:
    slug = commander if "-" in commander and " " not in commander else commander_to_slug(commander)
    return f"https://json.edhrec.com/pages/commanders/{slug}.json"


def _fetch_edhrec(commander: str) -> tuple[str, list[dict]]:
    """EDHREC commander page → (display_name, [{name, synergy, inclusion}]).

    GET json.edhrec.com/pages/commanders/<slug>.json (slug via commander_to_slug,
    mirroring simmander/sim/edhrec_fetcher.py). Records EDHREC's *own* published
    numbers verbatim — we do NOT recompute or renormalize synergy:

      * synergy   = cardview["synergy"] as published (raw float, may be negative).
      * inclusion = EDHREC's inclusion rate = num_decks / potential_decks, i.e.
                    the "X% of N decks" figure EDHREC itself displays. (The raw
                    `inclusion` field on the JSON is a deck *count*, not a rate;
                    the rate is what the contract example shows, and it is
                    EDHREC's own number — no statistics are computed here.)

    `commander` may be a display name or an already-formed slug. The returned
    display name is the commander page's own `header` (clean printed name).
    """
    data = _get_json(_edhrec_commander_url(commander))
    return _fetch_edhrec_from_blob(data, _edhrec_display_name(data, commander))


def _edhrec_display_name(data: dict, fallback: str) -> str:
    """Clean printed commander name from an EDHREC blob.

    EDHREC's page `header` carries a trailing role tag, e.g.
    'Krenko, Mob Boss (Commander)' / '... (Background)' — strip it so the name
    matches the `commander` field on deck records for downstream joins.
    """
    header = str(data.get("header") or fallback).strip()
    return re.sub(r"\s*\((?:Commander|Background|Partner)[^)]*\)\s*$", "", header).strip() or fallback


# ── EDHREC deckpreview discovery (real decklists, source-attributed) ──────────
#
# EDHREC's commander "decks" page lists real public decklists by urlhash; each
# deckpreview returns the full mainboard plus the canonical source URL
# (archidekt.com/decks/<id> or moxfield.com/decks/<publicId>). This is the
# breadth engine: it yields thousands of diverse, source-attributed decklists
# WITHOUT hammering Moxfield's Cloudflare-gated API.

def _edhrec_deck_hashes(commander: str, limit: int = 80) -> list[str]:
    slug = commander if "-" in commander and " " not in commander else commander_to_slug(commander)
    data = _get_json(f"https://json.edhrec.com/pages/decks/{slug}.json")
    table = data.get("table") or []
    out = [r.get("urlhash") for r in table if isinstance(r, dict) and r.get("urlhash")]
    return out[:limit]


def _parse_source_url(url: str) -> tuple[str, str] | None:
    """('moxfield.com/decks/AbC' | 'archidekt.com/decks/123') -> (source, id)."""
    if not url:
        return None
    m = re.search(r"archidekt\.com/decks/(\d+)", url)
    if m:
        return "archidekt", m.group(1)
    m = re.search(r"moxfield\.com/decks/([A-Za-z0-9_\-]+)", url)
    if m:
        return "moxfield", m.group(1)
    return None


def _fetch_edhrec_deckpreview(urlhash: str) -> tuple[str, str, str | None, list[str]] | None:
    """deckpreview/<urlhash> -> (source, native_id, commander, card_names)."""
    data = _get_json(f"https://edhrec.com/api/deckpreview/{urlhash}")
    src = _parse_source_url(data.get("url", ""))
    if not src:
        return None
    source, native_id = src
    cmdrs = data.get("commanders") or []
    commander = cmdrs[0] if cmdrs else None
    names: list[str] = []
    for line in data.get("deck", []) or []:
        m = re.match(r"^\s*\d+\s+(.*\S)\s*$", line)
        names.append((m.group(1) if m else line).strip())
    names = [n for n in names if n]
    return source, native_id, commander, names


# ── Seed commanders (top + diverse archetypes) ────────────────────────────────

def _edhrec_top_commanders(limit: int = 200) -> list[str]:
    """Names from EDHREC's 'Past 2 Years' top-commanders list (year.json)."""
    try:
        data = _get_json("https://json.edhrec.com/pages/commanders/year.json")
        cls = data["container"]["json_dict"]["cardlists"]
    except Exception:  # noqa: BLE001
        return []
    names: list[str] = []
    for cl in cls:
        for cv in cl.get("cardviews", []) or []:
            n = cv.get("name")
            if n:
                names.append(n)
    return names[:limit]


def _run_seeds(corpus: "Corpus", seeds: list[str], decks_per: int,
               expand_similar: bool, max_commanders: int) -> None:
    """Breadth driver: for each commander, write its EDHREC aggregate and pull
    up to `decks_per` real decklists via EDHREC deckpreview. Optionally widen the
    frontier with each commander's `similar` list."""
    queue = list(dict.fromkeys(seeds))
    visited: set[str] = set()
    while queue and len(visited) < max_commanders:
        commander = queue.pop(0)
        key = commander.lower()
        if key in visited:
            continue
        visited.add(key)
        display = commander

        # EDHREC aggregate + similar-commander expansion (one commander fetch).
        try:
            data = _get_json(_edhrec_commander_url(commander))
            display = _edhrec_display_name(data, commander)
            _, cards = _fetch_edhrec_from_blob(data, display)
            corpus.add_edhrec(display, cards)
            if expand_similar:
                for s in data.get("similar", []) or []:
                    if isinstance(s, str) and s.lower() not in visited:
                        queue.append(s)
        except Exception as e:  # noqa: BLE001
            print(f"[skip] edhrec-commander:{commander}: {e}", file=sys.stderr)

        # Real decklists for this commander.
        try:
            hashes = _edhrec_deck_hashes(commander, limit=decks_per)
        except Exception as e:  # noqa: BLE001
            print(f"[skip] edhrec-decks:{commander}: {e}", file=sys.stderr)
            hashes = []
        # Fetch deckpreviews concurrently (network-bound); the per-host limiter
        # keeps edhrec.com polite. Results are consumed serially on this thread,
        # so corpus writes need no lock.
        def _grab(h: str):
            try:
                return _fetch_edhrec_deckpreview(h)
            except Exception as e:  # noqa: BLE001
                print(f"[skip] deckpreview:{h}: {e}", file=sys.stderr)
                return None

        if hashes:
            with ThreadPoolExecutor(max_workers=6) as ex:
                for res in ex.map(_grab, hashes):
                    if res is None:
                        continue
                    source, nid, cmdr, names = res
                    corpus.add_deck(f"{source}:{nid}", source, cmdr, names)
        print(f"[seeds] {display}: {corpus._written} written so far "
              f"({len(visited)} commanders, {len(queue)} queued)",
              file=sys.stderr)


def _fetch_edhrec_from_blob(data: dict, display: str) -> tuple[str, list[dict]]:
    """Same parse as _fetch_edhrec but on an already-fetched commander blob
    (avoids a duplicate request in the seeds driver)."""
    try:
        cardlists = data["container"]["json_dict"]["cardlists"]
    except (KeyError, TypeError):
        cardlists = data.get("cardlists", []) or []
    seen: set[str] = set()
    cards: list[dict] = []
    for cl in cardlists:
        if not isinstance(cl, dict):
            continue
        for cv in cl.get("cardviews", cl.get("cards", []) or []):
            if not isinstance(cv, dict):
                continue
            name = cv.get("name") or cv.get("sanitized") or ""
            if not name or name in seen:
                continue
            num, pot = cv.get("num_decks"), cv.get("potential_decks")
            inclusion = round(num / pot, 6) if isinstance(num, (int, float)) and isinstance(pot, (int, float)) and pot else None
            cards.append({"name": name, "synergy": cv.get("synergy"), "inclusion": inclusion})
            seen.add(name)
    return display, cards


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Append raw decklists to the SP3 corpus.")
    ap.add_argument("source", choices=["archidekt", "moxfield", "edhrec", "seeds"])
    ap.add_argument("--id", help="single native deck id / commander name")
    ap.add_argument("--ids", help="comma-separated native ids / commander names")
    ap.add_argument("--batch", default="auto", help="batch label for the output filename")
    ap.add_argument("--decks-per", type=int, default=60,
                    help="[seeds] max real decklists to pull per commander")
    ap.add_argument("--max-commanders", type=int, default=120,
                    help="[seeds] stop after visiting this many commanders")
    ap.add_argument("--no-expand", action="store_true",
                    help="[seeds] do NOT widen via each commander's 'similar' list")
    ap.add_argument("--top", type=int, default=0,
                    help="[seeds] also seed from EDHREC's top-N commanders (year.json)")
    args = ap.parse_args()

    corpus = Corpus(batch=args.batch)

    if args.source == "seeds":
        seeds: list[str] = []
        if args.id:
            seeds.append(args.id)
        if args.ids:
            seeds += [x.strip() for x in args.ids.split(",") if x.strip()]
        if args.top:
            seeds += _edhrec_top_commanders(limit=args.top)
        if not seeds:
            ap.error("seeds: provide --id/--ids commander name(s) and/or --top N")
        _run_seeds(corpus, seeds, decks_per=args.decks_per,
                   expand_similar=not args.no_expand,
                   max_commanders=args.max_commanders)
        print(corpus.report(), file=sys.stderr)
        return 0

    ids = [args.id] if args.id else []
    if args.ids:
        ids += [x.strip() for x in args.ids.split(",") if x.strip()]
    if not ids:
        ap.error("provide --id or --ids")

    for nid in ids:
        try:
            if args.source == "archidekt":
                cmdr, names = _fetch_archidekt(nid)
                corpus.add_deck(f"archidekt:{nid}", "archidekt", cmdr, names)
            elif args.source == "moxfield":
                cmdr, names = _fetch_moxfield(nid)
                corpus.add_deck(f"moxfield:{nid}", "moxfield", cmdr, names)
            elif args.source == "edhrec":
                display, cards = _fetch_edhrec(nid)
                corpus.add_edhrec(display, cards)
        except Exception as e:  # noqa: BLE001 — keep going; report at end
            print(f"[skip] {args.source}:{nid}: {e}", file=sys.stderr)
    print(corpus.report(), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
