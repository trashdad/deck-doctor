"""End-to-end orchestrator behaviour, offline: real prep/build scripts on tiny fixtures,
fake network/rebuild/API. Covers ordering, nothing-to-do paths, gate failure, promote +
rollback, health/rebuild failure auto-rollback, crash recovery, resume, only/skip,
dry-run, approval gate and exit codes."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from card_update.fsutil import sha256_file
from card_update.lock import FileLock
from card_update.manifest import load_manifest

import harness as H

ALL = ["check", "fetch", "prep", "enrich", "build", "verify", "approve", "promote", "rebuild",
       "health", "cleanup"]


def _db_digest(path: Path) -> str:
    """Logical content of a SQLite file (the backup API may rewrite header bytes)."""
    import hashlib
    import sqlite3
    con = sqlite3.connect(path)
    try:
        return hashlib.sha256("\n".join(con.iterdump()).encode()).hexdigest()
    finally:
        con.close()


def _manifest(h: H.Harness):
    return load_manifest(h.run_dirs()[-1])


def _statuses(h: H.Harness) -> dict[str, str]:
    return {s.name: s.status for s in _manifest(h).stages}


# ── happy path ───────────────────────────────────────────────────────────────

def test_full_run_promotes_and_records_everything(h):
    before_sha = sha256_file(h.live_cards)
    code, out = h.main("run")
    assert code == 0, out
    st = _statuses(h)
    assert [s.name for s in _manifest(h).stages] == ALL          # ordered, all recorded
    assert all(st[n] == "ok" for n in ALL if n != "approve") and st["approve"] == "skipped"
    names = h.live_names()
    assert "Lightning Bolt" in names and "Treasure Token Fixture" not in names
    live = {c["name"]: c["id"] for c in json.loads(h.live_cards.read_text(encoding="utf-8"))}
    base = {c["name"]: c["id"] for c in json.loads((h.baseline / "cards.json").read_text(encoding="utf-8"))}
    assert live["Sol Ring"] == base["Sol Ring"] != H.SOL_RING_REPRINT     # id preserved over the reprint
    state = h.state()
    assert state["mtgish_sha"] == H.NEW_SHA and state["scryfall_updated_at"] == H.UPDATED_AT
    assert state["consecutive_failures"] == 0 and state["transaction"] is None
    assert state["current_release_id"] == _manifest(h).run_id
    backup = h.root / "card-data" / "releases" / "seed-1"
    assert sha256_file(backup / "cards.json") == before_sha
    prov = json.loads((h.live_cards.parent / "PROVENANCE.json").read_text(encoding="utf-8"))
    assert "MIT License" in prov["mtgish"]["license_text"] and prov["mtgish"]["sha"] == H.NEW_SHA
    calls = h.rebuild_calls()
    assert len(calls) == 1 and calls[0]["DD_DATA_LOCK_HELD"] == "1"
    assert "NEW CONTENT" in out and "Lightning Bolt" in out and "RESULT: PROMOTED" in out
    land = json.loads((h.live_cards.parent / "land_meta.json").read_text(encoding="utf-8"))
    assert land and all(v["produced_mana"] == ["G", "U"] for v in land.values())


def test_scryfall_ua_only_hits_expected_hosts(h):
    h.main("run")
    hosts = {u.split("/")[2] for _, u in h.fetcher.calls}
    assert hosts <= {"api.scryfall.com", "api.github.com", "data.scryfall.io", "raw.githubusercontent.com"}


# ── nothing to do ────────────────────────────────────────────────────────────

def test_nothing_to_do_when_upstream_unchanged(h):
    h.state_file.write_text(json.dumps({"mtgish_sha": H.NEW_SHA, "scryfall_updated_at": H.UPDATED_AT,
                                        "consecutive_failures": 2}), encoding="utf-8")
    code, out = h.main("run")
    assert code == 0 and "RESULT: nothing to do (stage check)" in out
    assert not any(c[0] == "DOWNLOAD" for c in h.fetcher.calls)
    st = h.state()
    assert st["consecutive_failures"] == 0 and st["last_success_utc"]
    assert _statuses(h) == {"check": "nothing_to_do"}          # later stages never started


def test_nothing_to_do_when_cards_identical_and_mtgish_same_records_new_stamp(h):
    assert h.main("run")[0] == 0
    h.fetcher.updated_at = "2026-11-27T10:00:00.000+00:00"
    h.clock.advance(86400)
    code, out = h.main("run")
    assert code == 0 and "RESULT: nothing to do (stage prep)" in out
    assert h.state()["scryfall_updated_at"] == "2026-11-27T10:00:00.000+00:00"
    assert len(h.rebuild_calls()) == 1                       # no second rebuild


# ── gates fail closed ─────────────────────────────────────────────────────────

def test_gate_violation_keeps_live_data_and_fails_loudly(h):
    h.overrides = {"gates": {"min_cards": 5, "sentinels": ["Sol Ring", "Black Lotus"]}}
    before = sha256_file(h.live_cards), sha256_file(h.live_scores)
    code, out = h.main("run")
    assert code == 1
    assert (sha256_file(h.live_cards), sha256_file(h.live_scores)) == before
    st = _statuses(h)
    assert st["verify"] == "failed" and "promote" not in st     # stopped before promote
    assert "Black Lotus" in out and "VIOLATION" in out and "live data unchanged" in out
    state = h.state()
    assert state["consecutive_failures"] == 1 and state["last_failure_stage"] == "verify"
    assert state["mtgish_sha"] == H.OLD_SHA                  # stamps NOT advanced: retried next run
    assert h.rebuild_calls() == []


def test_waived_gate_is_logged_but_does_not_block(h):
    h.overrides = {"gates": {"min_cards": 5, "sentinels": ["Black Lotus"]}}
    code, out = h.main("run", "--no-promote", "--waive", "sentinels")
    assert code == 0 and "WAIVED" in out


def test_download_failure_fails_before_touching_anything(h):
    h.fetcher.fail = {"data.scryfall.io"}
    before = sha256_file(h.live_cards)
    code, out = h.main("run")
    assert code == 1 and _statuses(h)["fetch"] == "failed"
    assert sha256_file(h.live_cards) == before


def test_changed_licence_fails_fetch(h):
    h.fetcher.license_text = "All rights reserved"
    code, out = h.main("run")
    assert code == 1 and "licence changed" in out


# ── post-promote failures roll back automatically ─────────────────────────────

def test_health_failure_rolls_back_files_rebuilds_and_exits_1(h):
    h.api.broken_counts = {11}                    # the new 11-card release breaks the API
    before = sha256_file(h.live_cards), _db_digest(h.live_scores)
    code, out = h.main("run")
    assert code == 1
    assert (sha256_file(h.live_cards), _db_digest(h.live_scores)) == before
    assert len(h.rebuild_calls()) == 2            # once for the release, once for the rollback
    state = h.state()
    assert state["current_release_id"] == "seed-1" and state["transaction"] is None
    assert state["mtgish_sha"] == H.OLD_SHA and state["consecutive_failures"] == 1
    assert _statuses(h)["promote"] == "rolled_back" and _statuses(h)["health"] == "failed"
    assert "RESOLVED: release seed-1 is live and healthy" in out and "rolled back to seed-1" in out


def test_rebuild_failure_rolls_back(h):
    h.rebuild_rcs[:] = [1, 0]
    before = sha256_file(h.live_cards)
    code, out = h.main("run")
    assert code == 1 and sha256_file(h.live_cards) == before
    assert _statuses(h)["rebuild"] == "failed" and _statuses(h).get("health") != "ok"


def test_failed_rollback_leaves_marker_for_next_run(h):
    h.rebuild_rcs[:] = [1, 1]
    code, out = h.main("run")
    assert code == 1 and "AUTOMATIC ROLLBACK" in out and "FAILED" in out
    assert h.state()["transaction"]["restore_to"] == "seed-1"
    assert "LIVE STATE UNRESOLVED" in out


def test_crashed_promotion_is_rolled_back_by_the_next_run(h):
    assert h.main("run")[0] == 0
    st = h.state()
    st["transaction"] = {"kind": "promote", "run_id": st["current_release_id"], "restore_to": "seed-1",
                         "needs_rebuild": True, "phase": "rebuilding", "started_utc": "2026-11-26T02:31:00Z"}
    h.state_file.write_text(json.dumps(st), encoding="utf-8")
    h.clock.advance(3600)
    code, out = h.main("run")
    assert code == 1 and "never completed" in out
    assert "Lightning Bolt" not in h.live_names()
    assert h.state()["transaction"] is None and h.state()["current_release_id"] == "seed-1"


def test_manual_rollback_command_restores_previous_release(h):
    assert h.main("run")[0] == 0
    promoted = h.state()["current_release_id"]
    code, out = h.main("rollback")
    assert code == 0, out
    assert "Lightning Bolt" not in h.live_names()
    assert h.state()["current_release_id"] == "seed-1"
    # the rolled-back release was snapshotted, so it can be restored again
    code, _ = h.main("rollback", "--to", promoted)
    assert code == 0 and "Lightning Bolt" in h.live_names()


# ── option handling ─────────────────────────────────────────────────────────────

def test_no_promote_builds_and_verifies_only(h):
    before = sha256_file(h.live_cards)
    code, out = h.main("run", "--no-promote")
    assert code == 0 and sha256_file(h.live_cards) == before
    st = _statuses(h)
    assert st["verify"] == "ok" and st["promote"] == "skipped" and st["cleanup"] == "skipped"
    wd = h.run_dirs()[-1]
    assert (wd / "cards.json").exists() and (wd / "scores.sqlite").exists()
    assert h.state()["mtgish_sha"] == H.OLD_SHA and h.rebuild_calls() == []


def test_no_promote_run_can_be_resumed_to_promote_the_same_candidate(h):
    assert h.main("run", "--no-promote")[0] == 0
    run_id = h.run_dirs()[-1].name
    assert _manifest(h).status == "partial"
    cand_sha = sha256_file(h.run_dirs()[-1] / "cards.json")
    code, out = h.main("run", "--resume", run_id)
    assert code == 0, out
    assert sha256_file(h.live_cards) == cand_sha and h.state()["current_release_id"] == run_id
    assert _manifest(h).status == "success"


def test_finished_run_cannot_be_resumed(h):
    assert h.main("run")[0] == 0
    assert h.main("run", "--resume", h.run_dirs()[-1].name)[0] == 2


def test_resume_continues_after_a_gate_failure(h):
    h.overrides = {"gates": {"min_cards": 5, "sentinels": ["Black Lotus"]}}
    assert h.main("run")[0] == 1
    run_id = h.run_dirs()[-1].name
    downloads = sum(1 for c in h.fetcher.calls if c[0] == "DOWNLOAD")
    h.overrides = {}
    code, out = h.main("run", "--resume", run_id)
    assert code == 0, out
    assert sum(1 for c in h.fetcher.calls if c[0] == "DOWNLOAD") == downloads   # nothing refetched
    assert "already done in this run" in out
    assert h.state()["current_release_id"] == run_id


def test_from_stage_requires_resume(h):
    assert h.main("run", "--from-stage", "verify")[0] == 2


def test_unknown_stage_is_usage_error(h):
    assert h.main("run", "--only", "bogus")[0] == 2


def test_only_with_skip_is_usage_error(h):
    assert h.main("run", "--only", "check", "--skip", "fetch")[0] == 2


def test_resume_of_unknown_run_is_usage_error(h):
    assert h.main("run", "--resume", "nope")[0] == 2


def test_only_check_runs_just_the_check(h):
    code, out = h.main("run", "--only", "check")
    assert code == 0
    st = _statuses(h)
    assert st["check"] == "ok" and all(st[n] == "skipped" for n in ALL[1:])
    assert h.state()["mtgish_sha"] == H.OLD_SHA        # partial run: no stamps, no success mark


def test_skip_enrich_keeps_live_land_meta(h):
    land_before = sha256_file(h.live_cards.parent / "land_meta.json")
    code, out = h.main("run", "--skip", "enrich")
    assert code == 0, out
    assert sha256_file(h.live_cards.parent / "land_meta.json") == land_before
    assert "Lightning Bolt" in h.live_names()


def test_dry_run_has_no_side_effects(h):
    code, out = h.main("run", "--dry-run")
    assert code == 0 and "DRY RUN" in out
    assert h.fetcher.calls == [] and h.run_dirs() == [] and h.rebuild_calls() == []
    for name in ALL:
        assert f"  {name:<8}" in out


def test_lock_timeout_exits_3(h):
    cfg = h.config()
    with FileLock(cfg.paths.lock_file, wait_s=0, clock=h.clock):
        code, out = h.main("run")
    assert code == 3 and "NOT RUN" in out
    assert h.fetcher.calls == []


def test_corrupt_state_fails(h):
    h.state_file.write_text("{oops", encoding="utf-8")
    assert h.main("run")[0] == 1


def test_approval_gate_blocks_until_file_exists_then_resume_promotes(h):
    h.overrides = {"approve": {"enabled": True}}
    code, out = h.main("run")
    assert code == 1 and "awaiting manual approval" in out
    run_id = h.run_dirs()[-1].name
    assert "Lightning Bolt" not in h.live_names()
    approvals = h.root / "card-data" / "approvals"
    approvals.mkdir(parents=True, exist_ok=True)
    (approvals / f"{run_id}.approved").write_text("", encoding="utf-8")
    code, out = h.main("run", "--resume", run_id)
    assert code == 0, out
    assert "Lightning Bolt" in h.live_names()


def test_custom_stage_plugs_in_and_a_crash_fails_cleanly(h):
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        order = ["check", "fetch", "prep", "plugin_stages:BoomStage", "build", "verify", "promote",
                 "rebuild", "health"]
        h.overrides = {"stages": {"order": order}}
        code, out = h.main("run")
    finally:
        sys.path.remove(str(Path(__file__).parent))
    assert code == 1 and "unexpected RuntimeError: boom" in out
    assert _statuses(h)["boom"] == "failed"


def test_cleanup_applies_retention(h):
    h.overrides = {"retention": {"keep_runs": 1, "keep_releases": 1}}
    assert h.main("run")[0] == 0
    h.clock.advance(86400)
    h.fetcher.updated_at = "2026-11-27T00:00:00.000+00:00"
    h.fetcher.mtgish_sha = "c" * 40
    assert h.main("run")[0] == 0
    assert len(h.run_dirs()) == 1
    rels = sorted(p.name for p in (h.root / "card-data" / "releases").iterdir())
    assert len(rels) == 1
