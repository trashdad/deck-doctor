import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

def test_relationship_determinism_subprocess(tmp_path):
    db_path = tmp_path / "scores.sqlite"
    con = sqlite3.connect(db_path)
    con.executescript("""
        CREATE TABLE cards (id TEXT PRIMARY KEY, name TEXT);
        CREATE TABLE card_fingerprints (card_id TEXT, ability_idx INT, record TEXT);
        CREATE TABLE card_flat_tags (card_id TEXT PRIMARY KEY, tags TEXT);
    """)
    
    fixture = Path(__file__).resolve().parent / "fixtures" / "relationships_store_cards.json"
    with open(fixture, encoding="utf-8") as f:
        cards = json.load(f)["cards"]
    
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from fingerprints.project import project_card
    from fingerprints.derive import flat_tags
    
    for c in cards:
        cid = c["id"]
        con.execute("INSERT INTO cards (id, name) VALUES (?, ?)", (cid, c["name"]))
        recs = project_card(c["mtgish"])
        for r in recs:
            con.execute("INSERT INTO card_fingerprints VALUES (?, ?, ?)",
                        (cid, r.ability_idx, json.dumps(r.to_dict())))
        tags = flat_tags(recs)
        con.execute("INSERT INTO card_flat_tags VALUES (?, ?)", (cid, json.dumps(list(tags))))
    con.commit()
    con.close()
    
    build_script = Path(__file__).resolve().parents[1] / "build_relationships.py"
    
    def run_build(seed):
        out_db = tmp_path / f"out_{seed}.sqlite"
        import shutil
        shutil.copy(db_path, out_db)
        env = dict(os.environ, PYTHONHASHSEED=str(seed))
        res = subprocess.run([sys.executable, str(build_script), "--db", str(out_db)], env=env, capture_output=True, text=True)
        assert res.returncode == 0, f"build failed:\n{res.stderr}"
        return out_db

    db1 = run_build(1)
    db2 = run_build(42)
    
    def get_tables(db):
        c = sqlite3.connect(db)
        rels = c.execute("SELECT * FROM card_relationships ORDER BY a, b").fetchall()
        engs = c.execute("SELECT * FROM engines ORDER BY engine_id").fetchall()
        c.close()
        return rels, engs
        
    r1, e1 = get_tables(db1)
    r2, e2 = get_tables(db2)
    
    assert len(r1) == len(r2), f"card_relationships counts differ: {len(r1)} vs {len(r2)}"
    assert r1 == r2, "card_relationships rows differ"
    assert len(e1) == len(e2), f"engines counts differ: {len(e1)} vs {len(e2)}"
    assert e1 == e2, "engines rows differ"
