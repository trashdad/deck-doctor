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
    # newest-first corpus growth (biases toward the current meta; resumable):
    python tools/scrape_decklists/runner.py recent --recent-source archidekt --max 1000
    python tools/scrape_decklists/runner.py recent --recent-source tappedout --max 1000
    python tools/scrape_decklists/runner.py recent --recent-source deckstats --max 1000
    python tools/scrape_decklists/runner.py recent --recent-source aetherhub --max 1000
    python tools/scrape_decklists/runner.py recent --recent-source manastack --max 1000
    python tools/scrape_decklists/runner.py recent --resume --max 2000   # continue a deep walk
    # commander-breadth discovery (not date-ordered):
    python tools/scrape_decklists/runner.py seeds --top 200 --decks-per 40
    # moxfield / edhrec sources: see _fetch_moxfield / _fetch_edhrec (driven by the
    # delegated LLM, which fills in the site-specific request/parse per PROMPT.md).

New sources (2026-06-11):
  tappedout  — TappedOut.net EDH listing + ?fmt=txt text export per deck
               Listing: tappedout.net/mtg-decks/search/?q=&format=edh&order=-date_updated&p=N
               Deck:    tappedout.net/mtg-decks/<slug>/?fmt=txt
  deckstats  — Deckstats.net EDH/Commander listing (cloudscraper) + JSON API per deck
               Listing: deckstats.net/decks/f/edh-commander/?page=N  (HTML, cloudflare)
               Deck:    deckstats.net/api.php?action=get_deck&id_type=saved&owner_id=OID&id=DID&response_type=json
  aetherhub  — AetherHub.com featured Commander listing (POST DataTables API, cloudscraper)
               Listing: aetherhub.com/Meta/FetchMetaListAdv?formatId=3  (POST, 17 featured decks)
               Deck:    aetherhub.com/Deck/FetchMtgaDeckJson?deckId=N&langId=0&simple=False
               NOTE: AetherHub's public listing is a curated 17-deck meta showcase.  We page
               through it using popular card searches to widen coverage.
  manastack  — ManaStack.com (React SPA) random-sample of recent Commander decks
               Deck:    manastack.com/api/deck?id=N  (Commander formatId=4)
               Listing: no public listing API — we scan recent IDs in descending order with
               a stride that balances coverage vs. wasted requests (most IDs are Casual/private).
"""

from __future__ import annotations

import argparse
import json
import random
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
    # New sources (2026-06-11) — conservative intervals per host tolerance
    "tappedout.net": 2.0,     # HTML site, no CDN buffer — polite
    "deckstats.net": 1.5,     # Cloudflare-lite; API is tolerant but be conservative
    "aetherhub.com": 2.0,     # Cloudflare-gated, DataTable POST API
    "manastack.com": 2.5,     # React SPA with no public listing; scan slowly
}
_DEFAULT_INTERVAL = 1.0
_host_lock = threading.Lock()
_host_last: dict[str, float] = {}

# ── Cloudscraper session (shared, lazy-init) ──────────────────────────────────
# Used by Cloudflare-gated sites (Deckstats, AetherHub, ManaStack, TappedOut).
# Falls back gracefully if cloudscraper is not installed (callers catch exceptions).
_cs_lock = threading.Lock()
_cs_session = None   # type: ignore[assignment]


def _cloudscraper() -> "cloudscraper.CloudScraper":  # noqa: F821
    global _cs_session
    if _cs_session is None:
        with _cs_lock:
            if _cs_session is None:
                import cloudscraper as _cs  # type: ignore[import]
                sess = _cs.create_scraper()
                sess.headers.update({"User-Agent": _UA})
                _cs_session = sess
    return _cs_session


def _cs_get(url: str, timeout: int = 30, **kwargs) -> "requests.Response":  # noqa: F821
    """GET via cloudscraper with per-host throttle.  Returns the Response object
    (not already-parsed JSON) so callers can check status and parse as needed."""
    _throttle(urllib.parse.urlparse(url).hostname or "")
    return _cloudscraper().get(url, timeout=timeout, **kwargs)


def _cs_post(url: str, timeout: int = 30, **kwargs) -> "requests.Response":  # noqa: F821
    """POST via cloudscraper with per-host throttle."""
    _throttle(urllib.parse.urlparse(url).hostname or "")
    return _cloudscraper().post(url, timeout=timeout, **kwargs)

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


# ── TappedOut ─────────────────────────────────────────────────────────────────
#
# Deck export: GET tappedout.net/mtg-decks/<slug>/?fmt=txt
# Returns a plain-text "N CardName" list.  The Commander zone is labelled with
# a leading "*CMDR* " prefix in the text export OR can be found by checking the
# HTML board-container (section heading "Commander").  The ?fmt=txt endpoint
# returns the plain-text list without any zone labels, but the page HTML does
# mark the commander clearly.  We use the HTML route because ?fmt=txt omits
# zone information; the board-container HTML is simple to parse.
#
# Listing: tappedout.net/mtg-decks/search/?q=&format=edh&order=-date_updated&p=N
# Pagination via p= query param.  Each page shows ~20 decks as slug links.

def _fetch_tappedout(native_id: str) -> tuple[str | None, list[str]]:
    """Fetch one TappedOut deck by slug.  native_id is the URL slug, e.g.
    'mana-flooding-is-a-good-thing'.  Returns (commander|None, card_names)."""
    try:
        from bs4 import BeautifulSoup  # type: ignore[import]
        r = _cs_get(f"https://tappedout.net/mtg-decks/{native_id}/", timeout=30)
        if r.status_code != 200:
            print(f"[tappedout] deck {native_id}: HTTP {r.status_code}", file=sys.stderr)
            return None, []
        soup = BeautifulSoup(r.text, "html.parser")
        board = soup.find("div", class_="board-container")
        if not board:
            return None, []

        # Quantities: <a class="qty board" data-name="..." data-qty="N">
        quantities: dict[str, int] = {}
        for tag in board.find_all("a", class_="qty", attrs={"data-name": True, "data-qty": True}):
            try:
                quantities[tag["data-name"]] = int(tag["data-qty"])
            except (ValueError, KeyError):
                pass

        # Zone tags: walk card-hover links and check the preceding h3 section header
        commander: str | None = None
        in_commander_section = False
        for node in board.find_all(True):
            if node.name == "h3":
                raw = re.sub(r"\s*\(\d+\)$", "", node.get_text()).strip().lower()
                in_commander_section = (raw in ("commander", "commanders"))
            elif node.name == "a" and "card-hover" in (node.get("class") or []):
                cname = node.get("data-name", "").strip()
                if cname and in_commander_section and commander is None:
                    commander = cname

        names = list(quantities.keys())
        return commander, names
    except Exception as e:  # noqa: BLE001
        print(f"[tappedout] fetch {native_id} error: {e}", file=sys.stderr)
        return None, []


def _tappedout_recent_page(page: int, pagesize: int = 20) -> tuple[list[str], bool]:
    """List TappedOut EDH deck slugs, newest-updated first.
    Returns (slugs, has_next). pagesize is unused (site returns ~20/page)."""
    try:
        from bs4 import BeautifulSoup  # type: ignore[import]
        url = (f"https://tappedout.net/mtg-decks/search/"
               f"?q=&format=edh&order=-date_updated&p={page}")
        r = _cs_get(url, timeout=30)
        if r.status_code != 200:
            print(f"[tappedout] listing page {page}: HTTP {r.status_code}", file=sys.stderr)
            return [], False
        soup = BeautifulSoup(r.text, "html.parser")
        slugs: list[str] = []
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            m = re.match(r"^/mtg-decks/([\w-]+)/$", a["href"])
            if m:
                slug = m.group(1)
                if slug not in seen and slug != "search":
                    slugs.append(slug)
                    seen.add(slug)
        # Detect next page: if we got any results and p=N+1 link exists
        next_link = soup.find("a", href=re.compile(rf"p={page + 1}"))
        has_next = bool(next_link) or len(slugs) >= 15
        return slugs, has_next
    except Exception as e:  # noqa: BLE001
        print(f"[tappedout] listing page {page} error: {e}", file=sys.stderr)
        return [], False


# ── Deckstats ─────────────────────────────────────────────────────────────────
#
# Listing: deckstats.net/decks/f/edh-commander/?page=N   (HTML, CF-lite)
# Each page lists ~20 decks; deck URLs are /decks/<owner_id>/<deck_id>-<slug>/.
# Deck: deckstats.net/api.php?action=get_deck&id_type=saved&owner_id=OID&id=DID&response_type=json
# Response has sections[].cards[]{name, amount, isCommander}.

def _fetch_deckstats(native_id: str) -> tuple[str | None, list[str]]:
    """Fetch one Deckstats deck.  native_id = '<owner_id>:<deck_id>' where
    deck_id is the bare integer (prefix before the slug hyphen).
    Returns (commander|None, card_names)."""
    try:
        parts = native_id.split(":", 1)
        if len(parts) != 2:
            return None, []
        owner_id, deck_id = parts
        url = (f"https://deckstats.net/api.php"
               f"?action=get_deck&id_type=saved&owner_id={owner_id}&id={deck_id}&response_type=json")
        r = _cs_get(url, timeout=30)
        if r.status_code != 200:
            print(f"[deckstats] deck {native_id}: HTTP {r.status_code}", file=sys.stderr)
            return None, []
        data = r.json()
        commander: str | None = None
        names: list[str] = []
        for section in data.get("sections", []) or []:
            for card in section.get("cards", []) or []:
                cname = (card.get("name") or "").strip()
                if not cname:
                    continue
                if card.get("isCommander") and commander is None:
                    commander = cname
                names.append(cname)
        # Also include sideboard/tokens only if they contain commander marker
        # (rare, but some users put companion in sideboard with isCommander)
        for extra_key in ("sideboard",):
            for card in (data.get(extra_key) or []):
                cname = (card.get("name") or "").strip()
                if cname and card.get("isCommander") and commander is None:
                    commander = cname
        return commander, names
    except Exception as e:  # noqa: BLE001
        print(f"[deckstats] fetch {native_id} error: {e}", file=sys.stderr)
        return None, []


def _deckstats_recent_page(page: int, pagesize: int = 20) -> tuple[list[str], bool]:
    """List Deckstats EDH Commander deck IDs, newest first.
    Returns (native_ids_as_'owner:deck_id', has_next)."""
    try:
        from bs4 import BeautifulSoup  # type: ignore[import]
        url = f"https://deckstats.net/decks/f/edh-commander/?lng=en&page={page}"
        r = _cs_get(url, timeout=30)
        if r.status_code != 200:
            print(f"[deckstats] listing page {page}: HTTP {r.status_code}", file=sys.stderr)
            return [], False
        soup = BeautifulSoup(r.text, "html.parser")
        ids: list[str] = []
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            m = re.match(r"https://deckstats\.net/decks/(\d+)/(\d+)[-\w]*/", a["href"])
            if m:
                owner_id, deck_id = m.group(1), m.group(2)
                nid = f"{owner_id}:{deck_id}"
                if nid not in seen:
                    ids.append(nid)
                    seen.add(nid)
        # Check for next page: site has up to 500 pages
        has_next = bool(soup.find("a", href=re.compile(rf"page={page + 1}"))) or len(ids) >= 15
        return ids, has_next
    except Exception as e:  # noqa: BLE001
        print(f"[deckstats] listing page {page} error: {e}", file=sys.stderr)
        return [], False


# ── AetherHub ─────────────────────────────────────────────────────────────────
#
# AetherHub's public Commander "meta" listing is a curated showcase of ~17 decks
# served via POST /Meta/FetchMetaListAdv?formatId=3 (DataTables server-side).
# There is no paginated public listing of all user Commander decks accessible
# without login.  We compensate by:
#   (a) fetching the 17-deck meta list,
#   (b) using card-name search strings (popular Commander staples) to retrieve
#       additional distinct community decks — each search yields up to 17 decks
#       with different results depending on the card filter.
# This approach yields hundreds of real Commander decks per crawl pass without
# requiring authentication or hammering any single endpoint.
#
# Per-deck: POST FetchMetaListAdv gives the numeric deckId; then
#   GET /Deck/FetchMtgaDeckJson?deckId=N&langId=0&simple=False
# returns convertedDeck[]{quantity, name} with category labels (Commander, etc.).

_AETHERHUB_FORMAT_COMMANDER = 3
_AETHERHUB_STAPLES = [
    # Common Commander staples — each yields a different subset of ~17 decks
    "Sol Ring", "Command Tower", "Arcane Signet", "Counterspell", "Swords to Plowshares",
    "Path to Exile", "Brainstorm", "Rhystic Study", "Cyclonic Rift", "Nature's Lore",
    "Demonic Tutor", "Cultivate", "Kodama's Reach", "Lightning Greaves", "Swiftfoot Boots",
    "Reliquary Tower", "Fellwar Stone", "Mind's Eye", "Teferi's Protection", "Smothering Tithe",
]


def _aetherhub_dt_payload(draw: int = 1, search_card: str = "") -> dict:
    """Build the DataTables POST payload for /Meta/FetchMetaListAdv."""
    cols = [
        {"data": "name",         "name": "name",         "searchable": True,  "orderable": False, "search": {"value": "", "regex": False}},
        {"data": "color",        "name": "color",        "searchable": True,  "orderable": False, "search": {"value": "", "regex": False}},
        {"data": "tags",         "name": "tags",         "searchable": True,  "orderable": False, "search": {"value": "", "regex": False}},
        {"data": "rarity",       "name": "rarity",       "searchable": False, "orderable": False, "search": {"value": "", "regex": False}},
        {"data": "price",        "name": "price",        "searchable": False, "orderable": False, "search": {"value": "", "regex": False}},
        {"data": "views",        "name": "views",        "searchable": False, "orderable": True,  "search": {"value": "", "regex": False}},
        {"data": "exports",      "name": "exports",      "searchable": False, "orderable": True,  "search": {"value": "", "regex": False}},
        {"data": "updated",      "name": "updated",      "searchable": False, "orderable": True,  "search": {"value": "", "regex": False}},
        {"data": "updatedhidden","name": "updatedhidden","searchable": False, "orderable": False, "search": {"value": "", "regex": False}},
        {"data": "popularity",   "name": "popularity",   "searchable": False, "orderable": True,  "search": {"value": "", "regex": False}},
    ]
    return {
        "draw": draw,
        "start": 0,
        "length": 40,
        "order": [{"column": 9, "dir": "desc"}],
        "columns": cols,
        "search": {"value": search_card, "regex": False},
    }


def _fetch_aetherhub(native_id: str) -> tuple[str | None, list[str]]:
    """Fetch one AetherHub deck by numeric deckId.
    Returns (commander|None, card_names)."""
    try:
        url = (f"https://aetherhub.com/Deck/FetchMtgaDeckJson"
               f"?deckId={native_id}&langId=0&simple=False")
        r = _cs_get(url, timeout=30)
        if r.status_code != 200:
            print(f"[aetherhub] deck {native_id}: HTTP {r.status_code}", file=sys.stderr)
            return None, []
        data = r.json()
        converted = data.get("convertedDeck") or []
        commander: str | None = None
        names: list[str] = []
        last_category: str | None = None
        for entry in converted:
            qty = entry.get("quantity")
            name = (entry.get("name") or "").strip()
            if not qty:
                # Zero-quantity rows are section headers
                last_category = name
                continue
            if name and qty:
                if last_category == "Commander" and commander is None:
                    commander = name
                names.append(name)
        return commander, names
    except Exception as e:  # noqa: BLE001
        print(f"[aetherhub] fetch {native_id} error: {e}", file=sys.stderr)
        return None, []


def _aetherhub_recent_page(page: int, pagesize: int = 20) -> tuple[list[str], bool]:
    """List AetherHub Commander deck IDs via the DataTables meta list endpoint.
    Uses card-name search rotation to widen coverage beyond the base 17 decks.
    'page' here maps to the staple search index (not a true offset-pagination).
    Returns (native_ids[str], has_next)."""
    try:
        # page 1 = empty search (17 featured); pages 2..N+1 = staple-N search
        card_query = "" if page == 1 else _AETHERHUB_STAPLES[(page - 2) % len(_AETHERHUB_STAPLES)]
        payload = _aetherhub_dt_payload(draw=page, search_card=card_query)
        r = _cs_post(
            f"https://aetherhub.com/Meta/FetchMetaListAdv?formatId={_AETHERHUB_FORMAT_COMMANDER}",
            json=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=30,
        )
        if r.status_code != 200:
            print(f"[aetherhub] listing page {page}: HTTP {r.status_code}", file=sys.stderr)
            return [], False
        data = r.json()
        decks = data.get("metadecks") or []
        ids = [str(d["id"]) for d in decks if d.get("id")]
        # We have 20 staples + the empty pass = 21 virtual pages
        has_next = page <= len(_AETHERHUB_STAPLES)
        return ids, has_next
    except Exception as e:  # noqa: BLE001
        print(f"[aetherhub] listing page {page} error: {e}", file=sys.stderr)
        return [], False


# ── ManaStack ─────────────────────────────────────────────────────────────────
#
# ManaStack is a React SPA with no public deck-listing endpoint (the tables/saves
# API requires authentication).  Deck IDs are sequential integers; as of 2026-06
# the max is ~1.26M.  We exploit this by walking backward from the current ceiling
# with a stride (to avoid hitting every single ID) and filtering to:
#   - format.id == 4 (Commander)
#   - private == False
# The stride is calibrated so we sample broadly without hammering the API.
# When the current ceiling is unknown we probe to find it dynamically.
#
# Per-deck: GET manastack.com/api/deck?id=N  (Commander formatId=4)
# Returns {id, name, format:{id,name}, private, cards:[{card:{name},commander,
# sideboard,maybeboard}]}.

_MANASTACK_FORMAT_COMMANDER = 4
_MANASTACK_SCAN_STRIDE = 7       # step between probed IDs; prime to reduce clustering
_MANASTACK_MAX_ID_CACHE: list[int] = []   # mutable cache so workers share state


def _manastack_probe_max_id() -> int:
    """Binary-search for the current highest ManaStack deck ID."""
    if _MANASTACK_MAX_ID_CACHE:
        return _MANASTACK_MAX_ID_CACHE[0]
    lo, hi = 1_000_000, 2_000_000
    # Quick high-bound check
    try:
        r = _cs_get(f"https://manastack.com/api/deck?id={hi}", timeout=15)
        if r.status_code == 200:
            lo = hi
            hi = 3_000_000
    except Exception:  # noqa: BLE001
        pass
    while lo < hi - 100:
        mid = (lo + hi) // 2
        try:
            r = _cs_get(f"https://manastack.com/api/deck?id={mid}", timeout=15)
            if r.status_code == 200:
                lo = mid
            else:
                hi = mid
        except Exception:  # noqa: BLE001
            hi = mid
    _MANASTACK_MAX_ID_CACHE.append(lo)
    return lo


def _fetch_manastack(native_id: str) -> tuple[str | None, list[str]]:
    """Fetch one ManaStack deck by numeric ID string.
    Returns (commander|None, card_names); skips non-Commander / private decks."""
    try:
        r = _cs_get(f"https://manastack.com/api/deck?id={native_id}", timeout=30)
        if r.status_code == 404:
            return None, []
        if r.status_code != 200:
            print(f"[manastack] deck {native_id}: HTTP {r.status_code}", file=sys.stderr)
            return None, []
        data = r.json()
        # Skip non-Commander or private decks
        fmt_id = (data.get("format") or {}).get("id")
        if fmt_id != _MANASTACK_FORMAT_COMMANDER:
            return None, []
        if data.get("private", True):
            return None, []
        commander: str | None = None
        names: list[str] = []
        for entry in (data.get("cards") or []):
            if entry.get("sideboard") or entry.get("maybeboard"):
                continue
            cname = ((entry.get("card") or {}).get("name") or "").strip()
            if not cname:
                continue
            if entry.get("commander") and commander is None:
                commander = cname
            names.append(cname)
        return commander, names
    except Exception as e:  # noqa: BLE001
        print(f"[manastack] fetch {native_id} error: {e}", file=sys.stderr)
        return None, []


def _manastack_recent_page(page: int, pagesize: int = 20) -> tuple[list[str], bool]:
    """'List' ManaStack Commander decks by scanning recent IDs in descending order.
    page=1 starts from the current max ID; each subsequent page steps backward by
    pagesize * _MANASTACK_SCAN_STRIDE IDs.  Returns (candidate_ids, has_next).
    NOTE: many IDs will be Casual/private; _fetch_manastack filters those out.
    The _run_recent loop sees them as empty fetches and does not count them."""
    try:
        max_id = _manastack_probe_max_id()
        step = pagesize * _MANASTACK_SCAN_STRIDE
        start = max_id - (page - 1) * step
        if start <= 0:
            return [], False
        end = max(1, start - step)
        # Sample IDs in [end, start] with stride
        ids = [str(i) for i in range(start, end, -_MANASTACK_SCAN_STRIDE) if i > 0]
        has_next = end > 1
        return ids, has_next
    except Exception as e:  # noqa: BLE001
        print(f"[manastack] listing page {page} error: {e}", file=sys.stderr)
        return [], False


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


# ── Recency-driven discovery (newest-first; bias the corpus to the live meta) ─
#
# Archidekt's deck-search API supports recency ordering and is NOT Cloudflare-
# gated, so it is the primary newest-first source. We walk
#   archidekt.com/api/decks/v3/?orderBy=-updatedAt&formats=3
# from most-recently-updated backward, fetch each deck via _fetch_archidekt, and
# append. Dedup-by-deck_id makes this incremental + resumable: a plain re-run
# starts at page 1 and stops once it hits a run of already-seen pages (only decks
# updated since last time sort to the top), while --resume continues a deep walk
# from a saved page cursor. Archidekt caps a search at ~1000 results (the `next`
# link goes null), so one pass ingests up to the freshest ~1000 Commander decks.
#
# Moxfield's search sits behind the same Cloudflare gate as its deck API (HTTP
# 403 to non-browser clients), so its recency walk degrades to a logged skip and
# Archidekt carries the growth — exactly the fallback the design calls for.

ARCHIDEKT_FORMAT_COMMANDER = 3   # archidekt deckFormat id for Commander / EDH
_RECENT_PAGESIZE = 50


def _archidekt_recent_page(page: int, pagesize: int = _RECENT_PAGESIZE) -> tuple[list[str], bool]:
    """One page of Commander deck ids, most-recently-updated first; (ids, has_next)."""
    url = (f"https://archidekt.com/api/decks/v3/?orderBy=-updatedAt"
           f"&formats={ARCHIDEKT_FORMAT_COMMANDER}&pageSize={pagesize}&page={page}")
    data = _get_json(url)
    ids = [str(r["id"]) for r in (data.get("results") or []) if r.get("id")]
    return ids, bool(data.get("next"))


def _moxfield_recent_page(page: int, pagesize: int = _RECENT_PAGESIZE) -> tuple[list[str], bool]:
    """One page of Commander public-ids, newest first. Cloudflare-gated → usually raises."""
    url = (f"https://api2.moxfield.com/v2/decks/search?pageNumber={page}&pageSize={pagesize}"
           f"&sortType=updated&sortDirection=Descending&fmt=commander")
    data = _get_json(url, headers={"Accept": "application/json"})
    res = data.get("data") or []
    ids = [r["publicId"] for r in res if r.get("publicId")]
    return ids, page < int(data.get("totalPages") or 0)


# source -> (page lister, single-deck fetcher). Both fetchers return (commander, names).
# NOTE: "moxfield" is intentionally NOT in this registry.  Moxfield's API sits behind
# Cloudflare and their ToS discourages bulk scraping.  We collect Moxfield decklists
# indirectly via the EDHREC deckpreview path (_fetch_edhrec_deckpreview), which returns
# fully attributed Moxfield deck content without hitting Moxfield's servers directly.
_RECENT_SOURCES = {
    "archidekt": (_archidekt_recent_page, _fetch_archidekt),
    "tappedout": (_tappedout_recent_page, _fetch_tappedout),
    "deckstats": (_deckstats_recent_page, _fetch_deckstats),
    "aetherhub": (_aetherhub_recent_page, _fetch_aetherhub),
    "manastack": (_manastack_recent_page, _fetch_manastack),
}


def _recent_cursor(source: str) -> Path:
    return CORPUS_DIR / f".recent_cursor_{source}"


def _run_recent(corpus: "Corpus", source: str, max_decks: int, resume: bool,
                saturate_pages: int, pagesize: int = _RECENT_PAGESIZE) -> None:
    """Walk a source newest-first, appending decks until `max_decks` new ones are
    written, the source is exhausted, or `saturate_pages` consecutive pages add
    nothing new (the corpus has caught up to the live meta). Resumable via a saved
    page cursor; writes the cursor after every page so an interrupted walk continues."""
    pager, fetch = _RECENT_SOURCES[source]
    cursor = _recent_cursor(source)
    page = 1
    if resume and cursor.exists():
        try:
            page = max(1, int(cursor.read_text(encoding="utf-8").strip()))
        except (ValueError, OSError):
            page = 1
    fetched = 0
    dry_streak = 0

    while fetched < max_decks:
        try:
            ids, has_next = pager(page, pagesize)
        except Exception as e:  # noqa: BLE001 — degrade (esp. Moxfield Cloudflare)
            print(f"[recent] {source} page {page} failed: {e}", file=sys.stderr)
            break
        if not ids:
            print(f"[recent] {source}: page {page} empty — exhausted", file=sys.stderr)
            break

        # Skip decks we already hold BEFORE fetching (saves requests + drives the
        # saturation signal); fetch the rest concurrently (network-bound).
        todo = [nid for nid in ids if f"{source}:{nid}" not in corpus._seen]

        def _grab(nid: str):
            try:
                return nid, fetch(nid)
            except Exception as e:  # noqa: BLE001
                print(f"[recent] {source}:{nid} fetch failed: {e}", file=sys.stderr)
                return nid, None

        page_new = 0
        if todo:
            with ThreadPoolExecutor(max_workers=6) as ex:
                for nid, res in ex.map(_grab, todo):
                    if res is None:
                        continue
                    cmdr, names = res
                    if corpus.add_deck(f"{source}:{nid}", source, cmdr, names):
                        page_new += 1
                        fetched += 1
                        if fetched >= max_decks:
                            break

        cursor.write_text(str(page + 1), encoding="utf-8")
        print(f"[recent] {source} page {page}: +{page_new} new "
              f"({fetched} total, {len(ids) - len(todo)} already held)", file=sys.stderr)

        dry_streak = dry_streak + 1 if page_new == 0 else 0
        if dry_streak >= saturate_pages:
            print(f"[recent] {source}: {saturate_pages} dry pages — corpus is current; stopping",
                  file=sys.stderr)
            break
        if not has_next:
            print(f"[recent] {source}: no further pages (reached the search cap)", file=sys.stderr)
            break
        page += 1


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
    ap.add_argument("source", choices=["archidekt", "moxfield", "edhrec", "seeds", "recent"])
    ap.add_argument("--id", help="single native deck id / commander name")
    ap.add_argument("--ids", help="comma-separated native ids / commander names")
    ap.add_argument("--batch", default="auto", help="batch label for the output filename")
    ap.add_argument("--recent-source", default="archidekt",
                    choices=["archidekt", "tappedout", "deckstats", "aetherhub", "manastack"],
                    help="[recent] which site to walk newest-first")
    ap.add_argument("--max", type=int, default=1000,
                    help="[recent] stop after writing this many new decks")
    ap.add_argument("--saturate-pages", type=int, default=5,
                    help="[recent] stop after this many consecutive all-already-seen pages")
    ap.add_argument("--resume", action="store_true",
                    help="[recent] continue from the saved page cursor instead of page 1")
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

    if args.source == "recent":
        _run_recent(corpus, args.recent_source, max_decks=args.max,
                    resume=args.resume, saturate_pages=args.saturate_pages)
        print(corpus.report(), file=sys.stderr)
        return 0

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
