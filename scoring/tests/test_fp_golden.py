import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fingerprints.project import project_card  # noqa: E402
from fingerprints.qa import golden_diff  # noqa: E402

GOLDEN_DIR = Path(__file__).resolve().parents[2] / "data" / "golden"
MTGISH = Path("C:/simmander/simmander/mtgish/data/cards.json")


def _mtgish_by_name():
    return {c["Name"]: c for c in json.loads(MTGISH.read_text(encoding="utf-8"))
            if c.get("Name")}


def test_all_golden_match():
    if not GOLDEN_DIR.is_dir() or not list(GOLDEN_DIR.glob("*.json")):
        import pytest
        pytest.skip("no golden fixtures yet")
    if not MTGISH.is_file():
        import pytest
        pytest.skip("MTGish corpus not available on this machine")
    by_name = _mtgish_by_name()
    failures = []
    for f in sorted(GOLDEN_DIR.glob("*.json")):
        obj = json.loads(f.read_text(encoding="utf-8"))
        recs = project_card(by_name[obj["name"]])
        diff = golden_diff(recs, obj["records"])
        if diff:
            failures.append(f"{obj['name']}: {diff}")
    assert not failures, "\n".join(failures)
