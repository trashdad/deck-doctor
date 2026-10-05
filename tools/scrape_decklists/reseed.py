"""Re-collect real decklists for chosen commanders, newest-first, up to a target.

Written for the 2026-10 shell bug: 20,580 Moxfield decks were stored as the
deckpreview object's keys. They cannot be re-fetched by id (api2.moxfield.com
is Cloudflare-gated and the corpus keeps no EDHREC urlhash per deck), so for
each affected commander this walks EDHREC's deck listing (newest first) and
adds decks the corpus has not seen until `target` new decks are written or
`max_rows` listing rows have been read. Shells EDHREC still lists come back
as themselves once their ids are removed from .seen_deck_ids.

Usage:
    python tools/scrape_decklists/reseed.py --targets targets.tsv \
        [--uncounted archidekt_ids.txt] [--batch reseed] \
        [--cap-mult 3] [--cap-extra 150] [--workers 6]

targets.tsv: one "<commander name>\t<target>" per line. --uncounted lists
deck ids that are written if found but do not count toward a target (decks
another pass restores by id).
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import runner


def read_targets(path: Path) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        name, _, n = line.rpartition("\t")
        if name.strip() and int(n) > 0:
            out.append((name.strip(), int(n)))
    return out


def reseed_commander(corpus: runner.Corpus, commander: str, target: int, max_rows: int,
                     hashes_fn=runner._edhrec_deck_hashes,
                     preview_fn=runner._fetch_edhrec_deckpreview,
                     uncounted: set[str] | frozenset[str] = frozenset(),
                     workers: int = 6) -> dict:
    res = {"commander": commander, "target": target, "added": 0,
           "counted": 0, "scanned": 0, "failed": 0}
    try:
        hashes = hashes_fn(commander, limit=max_rows)
    except Exception as e:  # noqa: BLE001 — one commander must not stop the run
        res["error"] = f"listing: {e}"
        return res

    def _grab(h: str):
        try:
            return preview_fn(h)
        except Exception:  # noqa: BLE001
            return False

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        for i in range(0, len(hashes), max(1, workers)):
            for got in ex.map(_grab, hashes[i:i + workers]):
                res["scanned"] += 1
                if got is False:
                    res["failed"] += 1
                elif got is not None:
                    source, nid, cmdr, names = got
                    deck_id = f"{source}:{nid}"
                    if corpus.add_deck(deck_id, source, cmdr, names):
                        res["added"] += 1
                        if deck_id not in uncounted:
                            res["counted"] += 1
            # Checked per chunk: rows already fetched in this chunk are kept.
            if res["counted"] >= target:
                return res
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--targets", type=Path, required=True)
    ap.add_argument("--uncounted", type=Path)
    ap.add_argument("--batch", default="reseed")
    ap.add_argument("--cap-mult", type=int, default=3)
    ap.add_argument("--cap-extra", type=int, default=150)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    targets = read_targets(args.targets)
    uncounted: set[str] = set()
    if args.uncounted:
        uncounted = {ln.strip() for ln in args.uncounted.read_text(encoding="utf-8").splitlines()
                     if ln.strip()}
    corpus = runner.Corpus(batch=args.batch)
    totals = {"target": 0, "added": 0, "counted": 0, "scanned": 0, "failed": 0}
    for commander, target in targets:
        res = reseed_commander(corpus, commander, target,
                               max_rows=args.cap_mult * target + args.cap_extra,
                               uncounted=uncounted, workers=args.workers)
        print(json.dumps(res, ensure_ascii=False), flush=True)
        for k in totals:
            totals[k] += res[k]
    print(f"reseed totals: {json.dumps(totals)} over {len(targets)} commanders", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
