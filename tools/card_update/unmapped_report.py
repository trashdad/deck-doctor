"""Write the full occurrence-weighted unmapped-operator list for an MTGish file as JSON.

Standalone (run by repo_bridge in a child process): uses scoring/fingerprints/qa.py,
the same report build_fingerprints.py prints (top 25 only).

    python tools/card_update/unmapped_report.py --scoring-dir scoring --mtgish X --out Y
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scoring-dir", required=True)
    ap.add_argument("--mtgish", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    sys.path.insert(0, str(Path(a.scoring_dir).resolve()))
    from mtgish_schema import load_mtgish  # noqa: E402
    from fingerprints.qa import unmapped_operators  # noqa: E402

    ops = unmapped_operators(load_mtgish(a.mtgish))
    Path(a.out).write_text(json.dumps(ops), encoding="utf-8")
    print(f"unmapped operators: {len(ops)} distinct, {sum(n for _, n in ops)} occurrences")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
