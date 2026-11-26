"""Retention for run dirs, backup releases and per-run log files."""

from __future__ import annotations

import logging
import shutil
from datetime import timedelta
from typing import Any

from card_update.clock import Clock
from card_update.config import Config
from card_update.releases import ReleaseStore
from card_update.state import State


def protected_releases(state: State) -> set[str]:
    keep = {state.current_release_id} if state.current_release_id else set()
    if state.transaction:
        keep.add(str(state.transaction.get("restore_to")))
    return keep


def apply_retention(cfg: Config, state: State, releases: ReleaseStore, clock: Clock,
                    log: logging.Logger | logging.LoggerAdapter, current_run_id: str | None) -> dict[str, Any]:
    r = cfg.retention
    removed_releases = releases.prune(r.keep_releases, protected_releases(state))

    removed_runs: list[str] = []
    runs_dir = cfg.paths.runs_dir
    if runs_dir.exists():
        runs = sorted((p for p in runs_dir.iterdir() if p.is_dir()), key=lambda p: p.name, reverse=True)
        keep = {p.name for p in runs[:r.keep_runs]}
        pending = (state.transaction or {}).get("run_id")
        keep |= {x for x in (current_run_id, pending) if x}
        for p in runs:
            if p.name not in keep:
                shutil.rmtree(p)
                removed_runs.append(p.name)

    removed_logs: list[str] = []
    logs_dir = cfg.paths.logs_dir
    if logs_dir.exists():
        cutoff = (clock.now() - timedelta(days=r.keep_log_days)).timestamp()
        for p in logs_dir.glob("*.log"):
            if p.stat().st_mtime < cutoff and p.stem != current_run_id:
                p.unlink()
                removed_logs.append(p.name)

    for what, items in (("releases", removed_releases), ("runs", removed_runs), ("logs", removed_logs)):
        if items:
            log.info("retention removed %d old %s: %s", len(items), what, ", ".join(items))
    return {"releases": removed_releases, "runs": removed_runs, "logs": removed_logs}
