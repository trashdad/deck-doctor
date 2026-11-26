"""Live-side operations shared by the rebuild/health stages, transaction recovery and the
``rollback``/``recover`` commands: run deploy/rebuild_and_reload.sh, capture a pre-promote
baseline, and verify the live side (rebuilt tables + /health) against it.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

from card_update.clock import Clock
from card_update.config import Config
from card_update.http import FetchError, Fetcher
from card_update.procs import CommandResult, CommandRunner, CommandTimeout

# Built by rebuild_and_reload.sh (relationships, co-occurrence) and loaded into Postgres.
LIVE_TABLES = ("card_relationships", "engines", "card_cooccurrence")
# /health counters that must not collapse after a release (compared with the reading
# taken from the same API before promote; edhrec_commanders is 0 when the EDHREC kill
# switch is off, so it is only compared, never required to be > 0).
HEALTH_COUNTERS = ("engines", "edhrec_commanders", "spellbook_combos")


class OpsError(Exception):
    pass


def run_rebuild(cfg: Config, runner: CommandRunner, timeout_s: float | None = None) -> CommandResult:
    """build_relationships -> build_cooccurrence -> load_to_postgres -> POST /admin/reload.

    The caller holds the pipeline lock, so the script is told not to take it again.
    """
    script = cfg.paths.app_dir / cfg.rebuild.script
    env = {"DD_DATA_LOCK_HELD": "1", "APP_DIR": str(cfg.paths.app_dir), "PY": cfg.paths.python,
           "API": cfg.health.api_base, "LOG_TAG": "cardupdate"}
    try:
        res = runner.run([cfg.rebuild.bash, str(script)], cwd=cfg.paths.app_dir,
                         timeout_s=timeout_s or cfg.rebuild.timeout_minutes * 60,
                         label="rebuild_and_reload", env=env)
    except CommandTimeout as exc:
        raise OpsError(str(exc)) from None
    if res.returncode != 0:
        raise OpsError(f"{script} exited {res.returncode}; last output:\n    {res.tail_text()}")
    return res


def live_table_counts(scores: Path) -> dict[str, int | None]:
    """Row counts of the rebuilt tables in the live store (None = table absent)."""
    if not Path(scores).exists():
        return {t: None for t in LIVE_TABLES}
    con = sqlite3.connect(f"{Path(scores).resolve().as_uri()}?mode=ro", uri=True)
    try:
        have = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return {t: (con.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0] if t in have else None)
                for t in LIVE_TABLES}
    finally:
        con.close()


def capture_baseline(cfg: Config, api: Fetcher, log: logging.Logger | logging.LoggerAdapter) -> dict[str, Any]:
    """What the live side looks like before a promote (best effort for /health)."""
    base: dict[str, Any] = {"tables": live_table_counts(cfg.paths.live_scores), "health": None}
    try:
        body = api.get_json(cfg.health.api_base.rstrip("/") + "/health")
        if isinstance(body, dict):
            base["health"] = {k: body.get(k) for k in HEALTH_COUNTERS}
    except FetchError as exc:
        log.warning("pre-promote /health unavailable (%s); only non-zero checks after rebuild", exc)
    log.info("pre-promote baseline: %s", base)
    return base


def _shrunk(now: Any, before: Any, max_shrink: float) -> bool:
    return isinstance(before, int) and before > 0 and (not isinstance(now, int) or now < (1 - max_shrink) * before)


def table_problems(counts: dict[str, int | None], baseline: dict[str, Any] | None, max_shrink: float) -> list[str]:
    out = [f"{t} is missing or empty after rebuild" for t in LIVE_TABLES if not counts.get(t)]
    before = (baseline or {}).get("tables") or {}
    out += [f"{t} shrank from {before[t]:,} to {counts.get(t)} rows (max shrink {max_shrink:.0%})"
            for t in LIVE_TABLES if counts.get(t) and _shrunk(counts.get(t), before.get(t), max_shrink)]
    return out


def health_problem(body: Any, expected_cards: int, baseline: dict[str, Any] | None,
                   max_shrink: float) -> str | None:
    if not isinstance(body, dict):
        return f"unexpected body {body!r}"
    if body.get("status") != "ok":
        return f"status={body.get('status')!r}"
    if body.get("scores_loaded") is not True:
        return f"scores_loaded={body.get('scores_loaded')!r} (Postgres score tables missing?)"
    if body.get("cards") != expected_cards:
        return f"cards={body.get('cards')} but expected {expected_cards}"
    if not isinstance(body.get("engines"), int) or body["engines"] <= 0:
        return f"engines={body.get('engines')!r} (relationship engines not loaded)"
    before = (baseline or {}).get("health") or {}
    shrunk = [f"{k} {before[k]} -> {body.get(k)}" for k in HEALTH_COUNTERS
              if _shrunk(body.get(k), before.get(k), max_shrink)]
    if shrunk:
        return "counters collapsed vs before the release: " + ", ".join(shrunk)
    return None


def wait_healthy(cfg: Config, api: Fetcher, clock: Clock, log: logging.Logger | logging.LoggerAdapter,
                 expected_cards: int, baseline: dict[str, Any] | None = None) -> dict[str, Any]:
    url = cfg.health.api_base.rstrip("/") + "/health"
    deadline = clock.monotonic() + cfg.health.timeout_s
    problem = "no response yet"
    while True:
        try:
            body = api.get_json(url)
            problem = health_problem(body, expected_cards, baseline, cfg.health.max_shrink_ratio)
            if problem is None:
                log.info("API healthy: %s", body)
                return body
        except FetchError as exc:
            problem = str(exc)
        if clock.monotonic() >= deadline:
            raise OpsError(f"{url} not healthy after {cfg.health.timeout_s:.0f}s: {problem}")
        log.info("waiting for healthy API (%s)", problem)
        clock.sleep(cfg.health.poll_interval_s)


def verify_live(cfg: Config, api: Fetcher, clock: Clock, log: logging.Logger | logging.LoggerAdapter,
                expected_cards: int, baseline: dict[str, Any] | None = None) -> dict[str, Any]:
    """Rebuilt tables present and not collapsed, then /health ok with the expected cards."""
    counts = live_table_counts(cfg.paths.live_scores)
    log.info("live rebuilt tables: %s", counts)
    problems = table_problems(counts, baseline, cfg.health.max_shrink_ratio)
    if problems:
        raise OpsError("; ".join(problems))
    body = wait_healthy(cfg, api, clock, log, expected_cards, baseline)
    return {"tables": counts, "health": body}
