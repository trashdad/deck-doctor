"""SP7 acquisition — crawl Commander Spellbook variants via the paginated REST API.

SCAFFOLD — implement per docs/superpowers/plans/2026-06-10-sp6-sp11-roadmap.md §7.1.
stdlib-only (urllib.request, json, time, argparse, pathlib). NO third-party deps.

Binding protocol (verified against the live API on 2026-06-10):
- START_URL = "https://backend.commanderspellbook.com/variants/?limit=100"
- Response shape: {"count", "next", "previous", "results": [variant…]}; follow "next"
  until null. (~400 pages expected.)
- Variant fields used downstream (load_spellbook.py): id, status, spoiler, identity,
  legalities{commander: bool}, popularity, bracketTag, description, manaNeeded,
  easyPrerequisites, notablePrerequisites,
  uses[]: {card: {name, oracleId, …}, quantity, mustBeCommander, zoneLocations, …},
  produces[]: {feature: {name, …}, quantity}.
- Request header: User-Agent: simmander-deckbuilder/1.0. Throttle 0.5 s between requests.
  On HTTP 429/5xx: retry after 5 s, 10 s, 30 s; after 3 failures abort (state stays resumable).
- Output: append each variant as one JSON line to data/spellbook_raw.jsonl (relative to the
  repo root — resolve via Path(__file__).resolve().parents[2]).
- Resume: after EVERY page, write {"next": <url>, "pages_done": N} to
  data/spellbook_state.json. `--resume` reads it and continues from "next" (appending);
  without --resume, start fresh (truncate the jsonl + state).
- CLI: python tools/import_spellbook/runner.py [--resume] [--limit-pages N]
  Progress print every 10 pages: "page 120  variants 12000  next=…".
- Do NOT use the 517 MB bulk variants.json (cannot stream-parse with stdlib json).

After the crawl, run load_spellbook.py to build data/spellbook.sqlite.
"""

from __future__ import annotations

START_URL = "https://backend.commanderspellbook.com/variants/?limit=100"
THROTTLE_SECONDS = 0.5
RETRY_DELAYS = (5, 10, 30)
USER_AGENT = "simmander-deckbuilder/1.0"


def main() -> None:
    raise NotImplementedError("SP7 pending — roadmap §7.1")


if __name__ == "__main__":
    main()
