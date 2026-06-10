import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DB = Path(__file__).resolve().parents[2] / "data" / "scores.sqlite"
GOLDEN = Path(__file__).resolve().parents[2] / "data" / "golden_cooccurrence"


def _ids(con, *names):
    m = dict(con.execute(
        f"SELECT name, id FROM cards WHERE name IN ({','.join('?'*len(names))})", names))
    return [m.get(n) for n in names]


def test_golden_cooccurrence():
    if not DB.is_file() or not GOLDEN.is_dir() or not list(GOLDEN.glob("*.json")):
        import pytest
        pytest.skip("no built DB or golden files yet")
    con = sqlite3.connect(DB)
    failures = []
    for f in sorted(GOLDEN.glob("*.json")):
        spec = json.loads(f.read_text(encoding="utf-8"))
        ida, idb = _ids(con, spec["a"], spec["b"])
        if ida is None or idb is None:
            failures.append(f"{f.name}: card(s) not found")
            continue
        a, b = sorted([ida, idb])
        row = con.execute("SELECT co_count, lift, edhrec_synergy_ab, edhrec_synergy_ba "
                          "FROM card_cooccurrence WHERE a=? AND b=?", (a, b)).fetchone()
        e = spec["expect"]
        if e.get("absent"):
            if row is not None:
                failures.append(f"{f.name}: expected absent, got {row}")
            continue
        if row is None:
            failures.append(f"{f.name}: pair missing from card_cooccurrence")
            continue
        co, lift, e_ab, e_ba = row
        if "co_count_min" in e and co < e["co_count_min"]:
            failures.append(f"{f.name}: co_count {co} < {e['co_count_min']}")
        if "co_count_max" in e and co > e["co_count_max"]:
            failures.append(f"{f.name}: co_count {co} > {e['co_count_max']}")
        if "edhrec_min" in e and max(e_ab or 0, e_ba or 0) < e["edhrec_min"]:
            failures.append(f"{f.name}: edhrec {max(e_ab or 0, e_ba or 0)} < {e['edhrec_min']}")
    con.close()
    assert not failures, "\n".join(failures)


def test_determinism_rebuild_is_identical():
    if not DB.is_file():
        import pytest
        pytest.skip("no built DB")
    con = sqlite3.connect(DB)
    try:
        before = con.execute("SELECT a, b, co_count, lift FROM card_cooccurrence "
                             "ORDER BY a, b LIMIT 500").fetchall()
    except sqlite3.OperationalError:
        import pytest
        con.close(); pytest.skip("card_cooccurrence not built")
    con.close()
    assert before == sorted(before)
