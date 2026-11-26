from __future__ import annotations

import json
import logging
import sqlite3

import pytest

from card_update.releases import (CARDS, LAND_META, SCORES, LivePaths, ReleaseError,
                                  ReleaseStore)

LOG = logging.getLogger("t")


def _db(path, value):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE IF NOT EXISTS t (v TEXT)")
    con.execute("DELETE FROM t")
    con.execute("INSERT INTO t VALUES (?)", (value,))
    con.commit()
    con.close()


def _dbval(path):
    con = sqlite3.connect(path)
    try:
        return con.execute("SELECT v FROM t").fetchone()[0]
    finally:
        con.close()


@pytest.fixture
def env(tmp_path, clock):
    live = LivePaths(cards=tmp_path / "current" / "cards.json",
                     land_meta=tmp_path / "current" / "land_meta.json",
                     scores=tmp_path / "data" / "scores.sqlite")
    live.cards.parent.mkdir(parents=True)
    live.scores.parent.mkdir(parents=True)
    live.cards.write_text('[{"id": "old"}]', encoding="utf-8")
    live.land_meta.write_text('{"old": {}}', encoding="utf-8")
    _db(live.scores, "old")
    return live, ReleaseStore(tmp_path / "releases", live, clock, LOG), tmp_path


def _candidates(tmp_path):
    run = tmp_path / "runs" / "r1"
    run.mkdir(parents=True)
    (run / CARDS).write_text('[{"id": "new"}]', encoding="utf-8")
    (run / LAND_META).write_text('{"new": {}}', encoding="utf-8")
    _db(run / SCORES, "new")
    return {CARDS: run / CARDS, LAND_META: run / LAND_META, SCORES: run / SCORES}


def test_snapshot_install_and_restore_round_trip(env):
    live, store, tmp = env
    info = store.snapshot_live("baseline-1", {"mtgish_sha": "a" * 40})
    assert set(info.files) == {CARDS, LAND_META, SCORES}
    assert info.provenance["mtgish_sha"] == "a" * 40

    cands = _candidates(tmp)
    store.install(cands)
    assert json.loads(live.cards.read_text())[0]["id"] == "new"
    assert _dbval(live.scores) == "new"
    assert not any(p.exists() for p in cands.values())        # moved, not copied

    store.restore("baseline-1")
    assert json.loads(live.cards.read_text())[0]["id"] == "old"
    assert json.loads(live.land_meta.read_text()) == {"old": {}}
    assert _dbval(live.scores) == "old"


def test_snapshot_includes_uncheckpointed_wal_pages(env):
    live, store, _ = env
    con = sqlite3.connect(live.scores)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA wal_autocheckpoint=0")
    con.execute("UPDATE t SET v='in-wal'")
    con.commit()
    try:
        info = store.snapshot_live("r-wal", {})
    finally:
        con.close()
    assert _dbval(info.path / SCORES) == "in-wal"


def _live_with_pending_wal(live, tmp):
    """Live store whose -wal holds committed, un-checkpointed frames and NO open
    connection (what a killed writer leaves): build it elsewhere with a connection kept
    open, copy db + wal while it is open, then use the copies as the live files."""
    src = tmp / "walsrc.sqlite"
    con = sqlite3.connect(src)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA wal_autocheckpoint=0")
    con.execute("CREATE TABLE t (v TEXT)")
    con.execute("INSERT INTO t VALUES ('walled')")
    con.commit()
    import shutil
    shutil.copyfile(src, live.scores)
    shutil.copyfile(str(src) + "-wal", str(live.scores) + "-wal")
    con.close()
    wal = live.scores.parent / "scores.sqlite-wal"
    assert wal.stat().st_size > 0                       # precondition: real pending frames
    return wal


def test_prepare_live_sqlite_checkpoints_pending_wal_frames(env):
    from card_update.releases import prepare_live_sqlite
    live, _store, tmp = env
    wal = _live_with_pending_wal(live, tmp)
    prepare_live_sqlite(live.scores)
    assert not wal.exists()                              # checkpointed into the main file, sidecar gone
    assert _dbval(live.scores) == "walled"               # ...without losing the committed data


def test_install_never_leaves_an_old_wal_next_to_the_new_store(env):
    live, store, tmp = env
    wal = _live_with_pending_wal(live, tmp)
    store.install(_candidates(tmp))                      # a no-op prepare would leave the stale -wal here
    assert not wal.exists()
    assert _dbval(live.scores) == "new"


def test_snapshot_replacement_keeps_the_old_snapshot_until_the_new_one_is_in_place(env, monkeypatch):
    import os
    live, store, _tmp = env
    store.snapshot_live("r1", {"n": 1})
    real = os.replace
    calls = {"n": 0}

    def fail_second(a, b):
        calls["n"] += 1
        if calls["n"] == 3:      # 1 release.json write, 2 old snapshot aside, 3 new snapshot into place
            raise OSError("injected")
        return real(a, b)
    monkeypatch.setattr("card_update.releases.os.replace", fail_second)
    with pytest.raises(OSError):
        store.snapshot_live("r1", {"n": 2})
    monkeypatch.setattr("card_update.releases.os.replace", real)
    old = store.dir / ".r1.old"
    assert (old / "release.json").exists()               # previous snapshot still on disk, not deleted


def test_restore_refuses_when_disk_is_too_full(env, monkeypatch):
    live, store, tmp = env
    store.snapshot_live("r1", {})
    monkeypatch.setattr("card_update.releases.free_bytes", lambda p: 0)
    with pytest.raises(ReleaseError) as ei:
        store.restore("r1")
    assert "free disk space" in str(ei.value)


def test_restore_refuses_a_tampered_release_and_leaves_live_alone(env):
    live, store, tmp = env
    info = store.snapshot_live("r1", {})
    (info.path / CARDS).write_text("[]", encoding="utf-8")
    store.install(_candidates(tmp))
    with pytest.raises(ReleaseError):
        store.restore("r1")
    assert json.loads(live.cards.read_text())[0]["id"] == "new"


def test_restore_of_unknown_release_fails(env):
    _, store, _ = env
    with pytest.raises(ReleaseError):
        store.restore("nope")


def test_release_ids_cannot_escape_the_releases_dir(env):
    _, store, _ = env
    with pytest.raises(ReleaseError):
        store.snapshot_live("../evil", {})


def test_prune_keeps_newest_and_protected(env, clock):
    _, store, _ = env
    for i in range(5):
        store.snapshot_live(f"r{i}", {})
        clock.advance(60)
    removed = store.prune(keep=2, protect={"r0"})
    assert sorted(removed) == ["r1", "r2"]
    assert [r.release_id for r in store.list()] == ["r4", "r3", "r0"]


def test_install_rejects_unknown_names(env):
    _, store, tmp = env
    with pytest.raises(ReleaseError):
        store.install({"other.json": tmp / "x"})
