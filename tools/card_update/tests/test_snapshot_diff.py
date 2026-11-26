from __future__ import annotations

import json
import sqlite3

from card_update.diff import content_diff, render
from card_update.snapshot import finalize_sqlite, load_json_file, read_store


def _mkstore(path, rows, tags):
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE cards (id TEXT PRIMARY KEY, ier REAL)")
    con.execute("CREATE TABLE card_flat_tags (card_id TEXT PRIMARY KEY, tags TEXT)")
    con.executemany("INSERT INTO cards VALUES (?,?)", rows)
    con.executemany("INSERT INTO card_flat_tags VALUES (?,?)", tags)
    con.commit()
    con.close()


def test_read_store_collects_counts_tags_and_ier(tmp_path):
    p = tmp_path / "s.sqlite"
    _mkstore(p, [("a", 1.5), ("b", 2.0), ("c", None)],
             [("a", json.dumps(["e:draw"])), ("b", "[]")])
    snap = read_store(p, check_integrity=True)
    assert snap.integrity == "ok"
    assert snap.table_counts == {"cards": 3, "card_flat_tags": 2}
    assert snap.tagged_ids == {"a"} and snap.card_ids == {"a", "b", "c"}
    assert snap.ier["a"] == 1.5 and snap.ier["c"] is None


def test_finalize_sqlite_leaves_a_self_contained_file(tmp_path):
    p = tmp_path / "s.sqlite"
    _mkstore(p, [("a", 1.0)], [])
    finalize_sqlite(p)
    assert not (tmp_path / "s.sqlite-wal").exists()
    con = sqlite3.connect(p)
    assert con.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    con.close()


def test_load_json_file_reports_errors_instead_of_raising(tmp_path):
    p = tmp_path / "c.json"
    p.write_text("[1,", encoding="utf-8")
    data, err = load_json_file(p)
    assert data is None and "JSONDecodeError" in err


def _c(i, name, oid=None, set_="abc", **kw):
    d = {"id": f"id{i}", "oracle_id": oid or f"o{i}", "name": name, "set": set_}
    d.update(kw)
    return d


def test_content_diff_reports_new_removed_renamed_and_sets():
    cur = [_c(1, "Alpha"), _c(2, "Beta"), _c(3, "Gamma")]
    cand = [_c(1, "Alpha"), _c(2, "Beta Prime"), _c(4, "Delta", set_="new"), _c(5, "Eps", set_="abc")]
    d = content_diff(cur, cand)
    assert d.new_cards == [("Delta", "new"), ("Eps", "abc")]
    assert d.removed == ["Gamma"]
    assert d.renamed == [("Beta", "Beta Prime")]
    assert d.changed == 1
    assert d.new_set_codes == ["new"]
    text = "\n".join(render(d))
    assert "new cards: 2" in text and "new set codes: new" in text and "Beta -> Beta Prime" in text
