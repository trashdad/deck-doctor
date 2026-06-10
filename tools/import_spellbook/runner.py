"""SP7 acquisition — crawl Commander Spellbook variants via the paginated REST API.

stdlib-only. Writes each variant as one JSON line to data/spellbook_raw.jsonl.
Resumable: the last `next` URL is persisted to data/spellbook_state.json after
every page; --resume continues from it (appending).

Source (verified 2026-06-10): GET backend.commanderspellbook.com/variants/?limit=100
returns {count, next, previous, results}; follow `next` until null (~400 pages).

CLI: python tools/import_spellbook/runner.py [--resume] [--limit-pages N]
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_PATH = ROOT / "data" / "spellbook_raw.jsonl"
STATE_PATH = ROOT / "data" / "spellbook_state.json"

START_URL = "https://backend.commanderspellbook.com/variants/?limit=100"
THROTTLE_SECONDS = 1.2           # gentle sustained pace (API 429s under faster crawls)
RETRY_DELAYS = (15, 45, 120)     # long cooldowns — the rate-limit window is minutes, not seconds
USER_AGENT = "simmander-deckbuilder/1.0"

try:
    import certifi as _certifi
    _SSL_CTX = ssl.create_default_context(cafile=_certifi.where())
except ImportError:  # pragma: no cover
    _SSL_CTX = ssl.create_default_context()


def _get(url: str) -> dict:
    """GET JSON with retry/backoff on 429/5xx; raise after exhausting retries."""
    last_err: Exception | None = None
    for attempt, delay in enumerate((0, *RETRY_DELAYS)):
        if delay:
            time.sleep(delay)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60, context=_SSL_CTX) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code not in (429, 500, 502, 503, 504):
                raise
            print(f"  [retry {attempt}] HTTP {e.code}", file=sys.stderr)
        except (urllib.error.URLError, TimeoutError) as e:  # noqa: PERF203
            last_err = e
            print(f"  [retry {attempt}] {e}", file=sys.stderr)
    raise RuntimeError(f"giving up on {url}: {last_err}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Crawl Commander Spellbook variants.")
    ap.add_argument("--resume", action="store_true",
                    help="continue from data/spellbook_state.json (append)")
    ap.add_argument("--limit-pages", type=int, default=0,
                    help="stop after N pages (0 = all)")
    args = ap.parse_args()

    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    url = START_URL
    pages_done = 0
    mode = "a"
    if args.resume and STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text())
        url = state.get("next") or START_URL
        pages_done = state.get("pages_done", 0)
        print(f"resuming from page {pages_done} ({url})", file=sys.stderr)
    else:
        mode = "w"  # fresh crawl: truncate

    total = 0
    with RAW_PATH.open(mode, encoding="utf-8") as fh:
        while url:
            data = _get(url)
            for variant in data.get("results", []):
                fh.write(json.dumps(variant, ensure_ascii=False) + "\n")
                total += 1
            fh.flush()
            pages_done += 1
            url = data.get("next")
            STATE_PATH.write_text(json.dumps({"next": url, "pages_done": pages_done}))
            if pages_done % 10 == 0:
                print(f"page {pages_done}  variants {total}  next={'…' if url else 'DONE'}",
                      file=sys.stderr)
            if args.limit_pages and pages_done >= args.limit_pages:
                print(f"stopping after {pages_done} pages (--limit-pages)", file=sys.stderr)
                break
            time.sleep(THROTTLE_SECONDS)

    print(f"done: {pages_done} pages, {total} variants -> {RAW_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
