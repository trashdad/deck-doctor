"""Transactional promote / revert / recover (review findings 1, 2, 3, 7, 8, 10, 11, 12):
failure injection after each installed file, durable marker semantics, `recover`
(incl. the API's files-only ExecStartPre), cleanup failures, strengthened health,
fingerprint-scoped IER gate, unmapped-operator baseline, run deadline."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

from card_update import releases as releases_mod
from card_update.fingerprint import UNKNOWN, scoring_fingerprint
from card_update.fsutil import sha256_file
from card_update.lock import FileLock
from card_update.manifest import load_manifest

import harness as H


def _statuses(h):
    return {s.name: s.status for s in load_manifest(h.run_dirs()[-1]).stages}


def _live_digest(h) -> tuple[str, str]:
    return sha256_file(h.live_cards), sha256_file(h.live_cards.parent / "land_meta.json")


def _state(h, **fields):
    st = h.state()
    st.update(fields)
    h.state_file.write_text(json.dumps(st), encoding="utf-8")


# ── finding 1: promote failure mid-install is reverted, never "unchanged" ────────

@pytest.mark.parametrize("fail_on_call", [1, 2, 3])
def test_failure_after_each_installed_file_reverts_live_files(h, monkeypatch, fail_on_call):
    before = _live_digest(h)
    real = releases_mod.move_into_place
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == fail_on_call:
            raise OSError(f"injected failure installing file #{fail_on_call}")
        return real(src, dst)
    monkeypatch.setattr(releases_mod, "move_into_place", flaky)
    code, out = h.main("run")
    assert code == 1
    assert _live_digest(h) == before                       # every live file back to the backup
    st = h.state()
    assert st["transaction"] is None and st["current_release_id"] == "seed-1"
    assert "promotion reverted: live files restored to seed-1" in out
    assert "live data unchanged" not in out
    assert h.rebuild_calls() == []                          # Postgres never touched


def test_failure_after_all_files_installed_is_reverted(h, monkeypatch):
    from card_update.stages import promote as promote_mod
    before = _live_digest(h)

    def boom(*a, **k):
        raise OSError("disk full writing PROVENANCE.json")
    monkeypatch.setattr(promote_mod, "atomic_write_json", boom)
    code, out = h.main("run")
    assert code == 1 and _live_digest(h) == before and h.state()["transaction"] is None
    assert "promotion reverted" in out


def test_marker_is_durable_before_any_live_file_changes(h, monkeypatch):
    seen = {}
    real = releases_mod.move_into_place

    def spy(src, dst):
        seen.setdefault("txn", json.loads(h.state_file.read_text(encoding="utf-8"))["transaction"])
        return real(src, dst)
    monkeypatch.setattr(releases_mod, "move_into_place", spy)
    assert h.main("run")[0] == 0
    assert seen["txn"]["kind"] == "promote" and seen["txn"]["restore_to"] == "seed-1"
    assert seen["txn"]["needs_rebuild"] is False


def test_live_state_not_matching_the_recorded_release_blocks_promote(h):
    _state(h, cards_sha256="0" * 64)
    before = _live_digest(h)
    code, out = h.main("run")
    assert code == 1 and "is not the recorded release" in out and _live_digest(h) == before
    assert not (h.root / "card-data" / "releases" / "seed-1").exists()   # good backup never overwritten


# ── finding 7: cleanup failure is a warning, never a rollback ─────────────────────

def test_cleanup_failure_keeps_the_healthy_release(h, monkeypatch):
    from card_update.stages import cleanup as cleanup_mod

    def boom(*a, **k):
        raise OSError("EBUSY deleting an old release")
    monkeypatch.setattr(cleanup_mod, "apply_retention", boom)
    code, out = h.main("run")
    assert code == 0, out
    assert _statuses(h)["cleanup"] == "warning" and "WARNING (non-fatal)" in out
    assert h.state()["transaction"] is None and "Lightning Bolt" in h.live_names()
    h.clock.advance(3600)
    code, out = h.main("run")                               # next run: nothing to do, no rollback
    assert code == 0 and "nothing to do" in out and "Lightning Bolt" in h.live_names()


# ── finding 8: health sees empty/collapsed rebuilt tables and API counters ─────────

@pytest.mark.parametrize("rows,needle", [(0, "missing or empty"), (2, "shrank from 10 to 2")])
def test_empty_or_shrunk_rebuilt_tables_roll_back(h, rows, needle):
    h.rebuild_rows = [rows, 10]             # the release's rebuild is bad, the rollback's is fine
    before = _live_digest(h)
    code, out = h.main("run")
    assert code == 1 and needle in out
    assert _live_digest(h) == before and h.state()["transaction"] is None


def test_unhealthy_rollback_keeps_the_change_open(h):
    h.rebuild_rows = 0                      # even the restored release rebuilds empty tables
    code, out = h.main("run")
    assert code == 1 and "AUTOMATIC ROLLBACK" in out and h.state()["transaction"]["restore_to"] == "seed-1"


def test_collapsed_api_counter_rolls_back(h):
    h.api_after_rebuild = {"spellbook_combos": 0}
    code, out = h.main("run")
    assert code == 1 and "spellbook_combos 30 -> 0" in out and "Lightning Bolt" not in h.live_names()


def test_zero_engines_fails_health(h):
    h.api_after_rebuild = {"engines": 0}
    code, out = h.main("run")
    assert code == 1 and "engines=0" in out


def test_end_to_end_records_rebuilt_table_counts(h):
    assert h.main("run")[0] == 0
    rec = next(s for s in load_manifest(h.run_dirs()[-1]).stages if s.name == "health")
    assert rec.outputs["tables"] == {"card_relationships": 10, "engines": 10, "card_cooccurrence": 10}
    assert rec.outputs["health"]["engines"] == 50


# ── finding 2/3: recover command, manual rollback crash-safety ─────────────────────

def _mixed_live_with_marker(h, needs_rebuild: bool):
    """A run promoted, then the box died: live files new, marker open."""
    assert h.main("run")[0] == 0
    _state(h, transaction={"kind": "promote", "run_id": h.state()["current_release_id"], "restore_to": "seed-1",
                           "needs_rebuild": needs_rebuild, "phase": "installed", "started_utc": "x"})


def test_recover_files_only_restores_and_closes_when_postgres_untouched(h):
    _mixed_live_with_marker(h, needs_rebuild=False)
    code, out = h.main("recover", "--files-only")
    assert code == 0 and "RECOVER: resolved" in out
    assert "Lightning Bolt" not in h.live_names() and h.state()["transaction"] is None
    assert len(h.rebuild_calls()) == 1                      # only the original run's rebuild


def test_recover_files_only_keeps_marker_when_postgres_needs_rebuild(h):
    _mixed_live_with_marker(h, needs_rebuild=True)
    code, out = h.main("recover", "--files-only")
    assert code == 0 and "files-only" in out
    assert "Lightning Bolt" not in h.live_names() and h.state()["transaction"]["phase"] == "files_restored"
    code, out = h.main("recover")                           # full: rebuild + health, then closed
    assert code == 0 and h.state()["transaction"] is None and len(h.rebuild_calls()) == 2


def test_recover_files_only_never_touches_a_running_jobs_change(h):
    _mixed_live_with_marker(h, needs_rebuild=True)
    with FileLock(h.config().paths.lock_file, wait_s=0, clock=h.clock):
        code, out = h.main("recover", "--files-only")
    assert code == 0 and "owns the open change" in out and "Lightning Bolt" in h.live_names()


def test_recover_with_nothing_open_is_a_noop(h):
    code, out = h.main("recover", "--files-only")
    assert code == 0 and "nothing to do" in out


def test_rollback_no_rebuild_keeps_change_open_until_rebuilt(h):
    assert h.main("run")[0] == 0
    code, out = h.main("rollback", "--no-rebuild")
    assert code == 0 and "Lightning Bolt" not in h.live_names()
    assert h.state()["transaction"]["needs_rebuild"] is True
    assert h.main("status", "--offline")[0] == 1            # unresolved change is visible
    code, out = h.main("run")                               # next run finishes it (rebuild + health)
    assert code == 1 and h.state()["transaction"] is None and "restored release seed-1" in out


def test_status_shows_unresolved_change(h):
    _mixed_live_with_marker(h, needs_rebuild=True)
    code, out = h.main("status", "--offline")
    assert code == 1 and "UNRESOLVED CHANGE" in out


# ── finding 10: IER gate scoped to the scoring-code fingerprint ─────────────────────

def _drift_one_live_ier(h) -> None:
    con = sqlite3.connect(h.live_scores)
    con.execute("UPDATE cards SET ier = ier + 5 WHERE name = 'Counterspell'")
    con.commit()
    con.close()


def test_ier_drift_blocks_when_no_fingerprint_is_recorded(h):
    _drift_one_live_ier(h)
    code, out = h.main("run", "--no-promote")
    assert code == 1 and "ier_stability VIOLATION" in out and "first run): enforcing" in out


def test_ier_drift_blocks_when_scoring_code_is_unchanged(h):
    _drift_one_live_ier(h)
    _state(h, scoring_fingerprint=scoring_fingerprint(H.REPO))
    code, out = h.main("run", "--no-promote")
    assert code == 1 and "ier_stability VIOLATION" in out


@pytest.mark.parametrize("recorded", [UNKNOWN, "f" * 64])
def test_ier_drift_after_a_scoring_code_change_warns_and_promotes(h, recorded):
    _drift_one_live_ier(h)
    _state(h, scoring_fingerprint=recorded)
    code, out = h.main("run")
    assert code == 0, out
    assert "IER enforcement skipped" in out and "1 unchanged card(s) changed IER" in out
    assert h.state()["scoring_fingerprint"] == scoring_fingerprint(H.REPO)   # re-baselined
    prov = json.loads((h.live_cards.parent / "PROVENANCE.json").read_text(encoding="utf-8"))
    assert prov["scoring_fingerprint"] == scoring_fingerprint(H.REPO)


def test_init_baseline_from_store_records_unknown(h):
    h.live_cards.unlink()
    h.state_file.unlink()
    h.overrides = {"paths": {"seed_cards": str(h.baseline / "cards.json")}}
    assert h.main("init", "--baseline-from-store")[0] == 0
    assert h.state()["scoring_fingerprint"] == UNKNOWN


# ── finding 11: unmapped-operator baseline ──────────────────────────────────────────

def test_first_promote_records_the_unmapped_baseline_and_next_run_uses_it(h):
    code, out = h.main("run")
    assert code == 0 and "recording" in out
    st = h.state()
    path = h.root / "card-data" / "unmapped" / f"{st['unmapped_operators_sha256']}.json"
    assert path.exists() and len(json.loads(path.read_text(encoding="utf-8"))) == st["last_unmapped_operators"]
    h.clock.advance(86400)
    h.fetcher.mtgish_sha = "c" * 40
    code, out = h.main("run", "--force")
    assert code == 0, out
    gate = load_manifest(h.run_dirs()[-1]).stages
    verify = next(s for s in gate if s.name == "verify").outputs["gates"]["unmapped_operators"]
    assert verify["baseline"] == st["last_unmapped_operators"] and verify["new"] == 0


# ── finding 12: run deadline ─────────────────────────────────────────────────────────

def test_run_deadline_fails_the_next_stage(h):
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        h.overrides = {"stages": {"order": ["check", "plugin_stages:ClockJumpStage", "fetch", "prep", "build",
                                           "verify", "promote", "rebuild", "health"]}}
        code, out = h.main("run")
    finally:
        sys.path.remove(str(Path(__file__).parent))
    assert code == 1 and "run deadline of 12 h exceeded before stage fetch" in out
