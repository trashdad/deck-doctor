"""Build the MTGish file the card pipeline read before the upstream port: base snapshot + upstream gap-fill.

Since the port to the restructured upstream schema (mtgish_schema.py), build_semantics.py
and build_fingerprints.py read upstream data/mtgish.lines.json directly; this script is
kept to reproduce stores built from the merged file.

The base snapshot (simmander/mtgish/data/cards.json, 2026-04-28) is what every
existing card's tags and fingerprints were built from. Upstream
(https://github.com/i5jb/mtgish) has since restructured parts of its schema
(counters, exile, tokens, graveyards), so replacing the base wholesale would
change existing cards. This keeps every base entry and adds only the upstream
entries for cards the base does not have (new sets). Upstream is pinned to a
commit so the output is reproducible.

Usage:
    python scoring/mtgish_merge.py --upstream-commit <sha> \
        [--base C:/simmander/simmander/mtgish/data/cards.json] \
        [--upstream-file mtgish.lines.json] [--out data/mtgish.merged.json]

build_semantics.py / build_fingerprints.py then take --mtgish data/mtgish.merged.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

from build_semantics import norm_name

UPSTREAM_RAW = "https://raw.githubusercontent.com/i5jb/mtgish/{sha}/data/mtgish.lines.json"


def read_lines(path: Path) -> list[dict]:
    """mtgish.lines.json: one card object per line."""
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def merge(base: list[dict], upstream: list[dict]) -> tuple[list[dict], int]:
    """Base entries unchanged, plus upstream entries whose Name the base lacks."""
    have = {norm_name(c.get("Name") or "") for c in base} - {""}
    extra: list[dict] = []
    for c in upstream:
        key = norm_name(c.get("Name") or "")
        if key and key not in have:
            have.add(key)
            extra.append(c)
    return base + extra, len(extra)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base", default="C:/simmander/simmander/mtgish/data/cards.json")
    ap.add_argument("--upstream-commit", required=True, help="i5jb/mtgish commit sha")
    ap.add_argument("--upstream-file", help="local copy of data/mtgish.lines.json at that commit")
    ap.add_argument("--out", default="data/mtgish.merged.json")
    args = ap.parse_args()

    base_path = Path(args.base)
    base = json.loads(base_path.read_text(encoding="utf-8"))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if args.upstream_file:
        up_path = Path(args.upstream_file)
    else:
        up_path = Path(args.out).with_name(f"mtgish.lines.{args.upstream_commit[:12]}.json")
        url = UPSTREAM_RAW.format(sha=args.upstream_commit)
        print(f"downloading {url}", flush=True)
        urllib.request.urlretrieve(url, up_path)
    upstream = read_lines(up_path)

    merged, added = merge(base, upstream)
    out.write_text(json.dumps(merged, ensure_ascii=False), encoding="utf-8")
    source = {
        "base": str(base_path), "base_sha256": _sha256(base_path), "base_entries": len(base),
        "upstream_commit": args.upstream_commit, "upstream_file": str(up_path),
        "upstream_sha256": _sha256(up_path),
        "upstream_entries": len(upstream), "added_from_upstream": added, "merged_entries": len(merged),
        "added_names": [c["Name"] for c in merged[len(base):]],
    }
    out.with_name(out.name + ".source.json").write_text(json.dumps(source, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in source.items() if k != "added_names"}))


if __name__ == "__main__":
    main()
