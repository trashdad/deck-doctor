"""Golden relationship expectations + catalog-recall sanity.

Measures (similarity/synergy) are computed LIVE from the SP2 fingerprints so the
test is robust to top-K trimming in the persisted card_relationships table. The
combo flag is checked against the table (asserted combos are always persisted).
"""

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fingerprints.schema import AbilityRecord  # noqa: E402
from fingerprints.derive import fingerprint_to_vector  # noqa: E402
from relationships.resources import card_resources  # noqa: E402
from relationships.measures import similarity, synergy  # noqa: E402

DB = Path(__file__).resolve().parents[2] / "data" / "scores.sqlite"
GOLDEN = Path(__file__).resolve().parents[2] / "data" / "golden_relationships"


def _records_for(con, name):
    rows = con.execute(
        "SELECT cf.record FROM card_fingerprints cf JOIN cards c ON c.id = cf.card_id "
        "WHERE c.name = ? ORDER BY cf.ability_idx", (name,)).fetchall()
    return [AbilityRecord.from_dict(json.loads(r)) for (r,) in rows]


def _combo_flag(con, name_a, name_b):
    ids = dict(con.execute("SELECT name, id FROM cards WHERE name IN (?, ?)", (name_a, name_b)))
    if name_a not in ids or name_b not in ids:
        return None
    a, b = sorted([ids[name_a], ids[name_b]])
    row = con.execute("SELECT combo FROM card_relationships WHERE a=? AND b=?", (a, b)).fetchone()
    return bool(row[0]) if row else False


def test_golden_relationships():
    if not DB.is_file() or not GOLDEN.is_dir() or not list(GOLDEN.glob("*.json")):
        import pytest
        pytest.skip("no built DB or golden fixtures yet")
    con = sqlite3.connect(DB)
    failures = []
    for f in sorted(GOLDEN.glob("*.json")):
        spec = json.loads(f.read_text(encoding="utf-8"))
        ra, rb = _records_for(con, spec["a"]), _records_for(con, spec["b"])
        if not ra or not rb:
            failures.append(f"{f.name}: card(s) not found in corpus")
            continue
        e = spec["expect"]
        sim = similarity(fingerprint_to_vector(ra), fingerprint_to_vector(rb))
        ab, ba = synergy(card_resources(ra), card_resources(rb))
        syn = max(ab, ba)
        if "similarity_min" in e and sim < e["similarity_min"]:
            failures.append(f"{f.name}: similarity {sim} < {e['similarity_min']}")
        if "similarity_max" in e and sim > e["similarity_max"]:
            failures.append(f"{f.name}: similarity {sim} > {e['similarity_max']}")
        if "synergy_min" in e and syn < e["synergy_min"]:
            failures.append(f"{f.name}: synergy {syn} < {e['synergy_min']}")
        if "synergy_max" in e and syn > e["synergy_max"]:
            failures.append(f"{f.name}: synergy {syn} > {e['synergy_max']}")
        if "combo" in e and _combo_flag(con, spec["a"], spec["b"]) != e["combo"]:
            failures.append(f"{f.name}: combo flag != {e['combo']}")
    con.close()
    assert not failures, "\n".join(failures)


def test_catalog_combos_ingested():
    """Asserted catalog combos are ingested and their pairs are combo-flagged."""
    if not DB.is_file():
        import pytest
        pytest.skip("no built DB")
    con = sqlite3.connect(DB)
    n_asserted = con.execute("SELECT COUNT(*) FROM engines WHERE asserted_combo=1").fetchone()[0]
    n_combo_pairs = con.execute("SELECT COUNT(*) FROM card_relationships WHERE combo=1").fetchone()[0]
    con.close()
    assert n_asserted >= 50, f"expected >=50 asserted combos, got {n_asserted}"
    assert n_combo_pairs >= 50, f"expected >=50 combo-flagged pairs, got {n_combo_pairs}"


def test_miner_finds_real_resource_engine():
    """The structural miner produces real multi-card resource engines: a chain
    engine containing Blood Artist (an aristocrats death-payoff) must exist.
    (The miner finds resource engines/cycles; it is NOT expected to rediscover
    Commander-Spellbook combos, which are interaction-based, not resource-flow —
    those come from the catalog.)"""
    if not DB.is_file():
        import pytest
        pytest.skip("no built DB")
    con = sqlite3.connect(DB)
    ba = con.execute("SELECT id FROM cards WHERE name='Blood Artist'").fetchone()
    if ba is None:
        con.close()
        import pytest
        pytest.skip("Blood Artist not in corpus")
    ba_id = ba[0]
    n = sum(1 for (m,) in con.execute("SELECT members FROM engines WHERE kind='chain'")
            if ba_id in json.loads(m))
    con.close()
    assert n >= 1, "miner found no resource engine containing Blood Artist"
