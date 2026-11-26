"""Orchestrator: lock -> recover a crashed promotion if needed -> run the selected stages
in order, recording each in the run manifest -> update state -> exit code.

Exit codes: 0 success or nothing-to-do, 1 stage failure / gate violation, 2 usage or
config error, 3 lock timeout.
"""

from __future__ import annotations

import importlib
import logging
import secrets
from dataclasses import asdict
from pathlib import Path
from typing import IO, Callable

from card_update.clock import Clock
from card_update.config import Config, ConfigError
from card_update.context import DeadlineExceeded, MissingInput, RunContext, RunOptions, Services
from card_update.fsutil import utc_iso
from card_update.lock import FileLock, LockTimeout
from card_update.logging_setup import close_logger, make_run_logger, stage_logger
from card_update.manifest import Manifest, ManifestError, StageRecord, load_manifest
from card_update.txn import Recovery, RecoveryError
from card_update.releases import LivePaths, ReleaseStore
from card_update.state import State, StateError, load_state, save_state
from card_update.stages import BUILTIN_STAGES
from card_update.stages.base import Outcome, Stage, StageError, StageResult

EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_LOCKED = 0, 1, 2, 3

ServicesFactory = Callable[[logging.Logger], Services]


def default_run_id(clock: Clock) -> str:
    return clock.now().strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(2)


def resolve_stages(order: list[str]) -> list[Stage]:
    """Built-in names, or ``package.module:Class`` for a plugged-in Stage subclass."""
    out: list[Stage] = []
    for name in order:
        if name in BUILTIN_STAGES:
            out.append(BUILTIN_STAGES[name]())
            continue
        module, _, cls_name = name.partition(":")
        try:
            cls = getattr(importlib.import_module(module), cls_name)
        except (ImportError, AttributeError) as exc:
            raise ConfigError(f"stages.order: cannot load custom stage {name!r}: {exc}") from None
        if not (isinstance(cls, type) and issubclass(cls, Stage) and cls.name):
            raise ConfigError(f"stages.order: {name!r} is not a Stage subclass with a name")
        out.append(cls())
    return out


def _base(log: logging.Logger | logging.LoggerAdapter) -> logging.Logger:
    """The run logger without a stage prefix."""
    return log.logger if isinstance(log, logging.LoggerAdapter) else log


def live_paths(cfg: Config) -> LivePaths:
    return LivePaths(cards=cfg.paths.live_cards, land_meta=cfg.paths.live_land_meta, scores=cfg.paths.live_scores)


class Pipeline:
    def __init__(self, config: Config, clock: Clock, services_factory: ServicesFactory,
                 stages: list[Stage] | None = None,
                 run_id_factory: Callable[[Clock], str] = default_run_id,
                 stream: IO[str] | None = None) -> None:
        self.cfg = config
        self.clock = clock
        self.services_factory = services_factory
        self.stages = stages if stages is not None else resolve_stages(config.stages.order)
        self.run_id_factory = run_id_factory
        self.stream = stream
        self.names = [s.name for s in self.stages]

    # ── option handling ─────────────────────────────────────────────────────
    def validate(self, opts: RunOptions) -> None:
        unknown = [n for n in (*opts.only, *opts.skip, *([opts.from_stage] if opts.from_stage else []))
                   if n not in self.names]
        if unknown:
            raise ConfigError(f"unknown stage(s) {unknown}; stages: {', '.join(self.names)}")
        if opts.only and (opts.skip or opts.from_stage):
            raise ConfigError("--only cannot be combined with --skip or --from-stage")
        if opts.from_stage and opts.from_stage != self.names[0] and not opts.resume:
            raise ConfigError(f"--from-stage {opts.from_stage} needs --resume <run-id>: its inputs live in "
                              "that run's directory")

    def plan(self, opts: RunOptions, manifest: Manifest | None) -> list[tuple[Stage, str | None]]:
        start = self.names.index(opts.from_stage) if opts.from_stage else 0
        verify_at = self.names.index("verify") if "verify" in self.names else len(self.names)
        out: list[tuple[Stage, str | None]] = []
        for i, st in enumerate(self.stages):
            reason = None
            if i < start:
                reason = f"before --from-stage {opts.from_stage}"
            elif opts.only and st.name not in opts.only:
                reason = "not in --only"
            elif st.name in opts.skip:
                reason = "--skip"
            elif opts.no_promote and i > verify_at:
                reason = "--no-promote"
            elif opts.resume and not opts.from_stage and manifest and manifest.stage_status(st.name) == "ok":
                reason = "already done in this run"
            out.append((st, reason))
        return out

    # ── entry point ─────────────────────────────────────────────────────────
    def run(self, opts: RunOptions) -> int:
        try:
            self.validate(opts)
        except ConfigError as exc:
            print(f"usage error: {exc}", file=self.stream)
            return EXIT_USAGE
        if opts.dry_run:
            return self._dry_run(opts)
        run_id = opts.resume or self.run_id_factory(self.clock)
        log = make_run_logger(run_id, self.cfg.paths.logs_dir / f"{run_id}.log", stream=self.stream)
        lock = FileLock(self.cfg.paths.lock_file, wait_s=self.cfg.lock.wait_minutes * 60,
                        clock=self.clock, log=log)
        try:
            try:
                lock.acquire()
            except LockTimeout as exc:
                log.error("RESULT: NOT RUN — %s", exc)
                return EXIT_LOCKED
            try:
                return self._run_locked(opts, run_id, log)
            finally:
                lock.release()
        finally:
            close_logger(log)

    def _dry_run(self, opts: RunOptions) -> int:
        log = make_run_logger("dry-run", None, stream=self.stream)
        try:
            state = load_state(self.cfg.paths.state_file)
        except StateError as exc:
            log.warning("state unreadable (%s); describing with empty state", exc)
            state = State()
        manifest = None
        if opts.resume:
            try:
                manifest = load_manifest(self.cfg.paths.runs_dir / opts.resume)
            except ManifestError as exc:
                log.error("%s", exc)
                close_logger(log)
                return EXIT_USAGE
        ctx = self._context("dry-run", self.cfg.paths.runs_dir / "<new-run>", state,
                            manifest or Manifest("dry-run", "", ""), opts, log)
        log.info("DRY RUN — no network, no files, no lock. Stage plan:")
        for st, reason in self.plan(opts, manifest):
            log.info("  %-8s %s", st.name, f"SKIP ({reason})" if reason else st.describe(ctx))
        close_logger(log)
        return EXIT_OK

    def _context(self, run_id: str, workdir: Path, state: State, manifest: Manifest, opts: RunOptions,
                 log: logging.Logger) -> RunContext:
        services = self.services_factory(log)
        releases = ReleaseStore(self.cfg.paths.releases_dir, live_paths(self.cfg), self.clock, log)
        return RunContext(config=self.cfg, run_id=run_id, workdir=workdir, state=state, manifest=manifest,
                          services=services, options=opts, log=log, releases=releases)

    def _open_run(self, opts: RunOptions, run_id: str) -> Manifest:
        workdir = self.cfg.paths.runs_dir / run_id
        if opts.resume:
            m = load_manifest(workdir)
            if m.status in ("success", "nothing_to_do"):
                raise ManifestError(f"run {run_id} already finished ({m.status}); start a new run")
            m.status, m.exit_code, m.finished_utc = "running", None, None
            m.options = {**m.options, "resumed_utc": utc_iso(self.clock.now()), "resume_options": asdict(opts)}
            return m
        workdir.mkdir(parents=True, exist_ok=False)
        return Manifest(run_id=run_id, workdir=str(workdir), created_utc=utc_iso(self.clock.now()),
                        options=asdict(opts))

    def _run_locked(self, opts: RunOptions, run_id: str, log: logging.Logger) -> int:
        try:
            state = load_state(self.cfg.paths.state_file)
        except StateError as exc:
            log.error("RESULT: FAILED — %s", exc)
            return EXIT_FAILED
        try:
            manifest = self._open_run(opts, run_id)
        except (ManifestError, FileExistsError) as exc:
            log.error("RESULT: NOT RUN — %s", exc)
            return EXIT_USAGE
        ctx = self._context(run_id, Path(manifest.workdir), state, manifest, opts, log)
        ctx.deadline = self.clock.monotonic() + self.cfg.run.deadline_hours * 3600
        log.info("card update run %s starting (config %s, workdir %s)", run_id, self.cfg.source, ctx.workdir)
        if state.transaction:
            return self._recover_open_transaction(ctx)
        manifest.save(ctx.workdir)

        for st, reason in self.plan(opts, manifest):
            if reason:
                if manifest.stage_status(st.name) != "ok":
                    manifest.record(StageRecord(name=st.name, status="skipped", summary=reason))
                log.info("[%s] skipped (%s)", st.name, reason)
                continue
            outcome = self._run_stage(ctx, st, log)
            if outcome is None:
                if not st.fatal:
                    continue                      # logged as a warning by _run_stage
                return self._finish_failed(ctx, st)
            if outcome.outcome is Outcome.NOTHING_TO_DO:
                return self._finish_nothing(ctx, st, outcome)
            if st.name == "health":
                self._commit(ctx, log)
        return self._finish_success(ctx)

    def _run_stage(self, ctx: RunContext, st: Stage, log: logging.Logger) -> StageResult | None:
        ctx.log = stage_logger(log, st.name)
        started, t0 = utc_iso(self.clock.now()), self.clock.monotonic()
        rec = StageRecord(name=st.name, status="running", started_utc=started)
        try:
            left = ctx.remaining_s()
            if left is not None and left <= 0:
                raise DeadlineExceeded(f"run deadline of {self.cfg.run.deadline_hours:g} h exceeded "
                                       f"before stage {st.name}")
            ctx.log.info("start: %s", st.describe(ctx))
            result = st.run(ctx)
        except (StageError, MissingInput, DeadlineExceeded) as exc:
            rec.error = str(exc)
        except Exception as exc:  # noqa: BLE001 - a bug or SIGTERM must still fail loudly + revert
            ctx.log.exception("unexpected error")
            rec.error = f"unexpected {type(exc).__name__}: {exc}"
        rec.ended_utc = utc_iso(self.clock.now())
        rec.duration_s = round(self.clock.monotonic() - t0, 2)
        if rec.error is not None:
            if st.fatal:
                rec.status = "failed"
                ctx.log.error("FAILED after %.1fs: %s", rec.duration_s, rec.error)
                ctx.extras["failed_message"] = rec.error
            else:
                rec.status = "warning"
                ctx.log.warning("non-fatal stage failed after %.1fs (run continues): %s", rec.duration_s, rec.error)
                ctx.extras.setdefault("warnings", []).append(f"{st.name}: {rec.error}")
            ctx.manifest.record(rec)
            ctx.manifest.save(ctx.workdir)
            return None
        rec.status, rec.summary, rec.outputs = result.outcome.value, result.summary, result.outputs
        ctx.log.info("%s in %.1fs: %s", result.outcome.value, rec.duration_s, result.summary)
        ctx.manifest.record(rec)
        ctx.manifest.save(ctx.workdir)
        return result

    # -- transaction ----------------------------------------------------------
    def _own_txn(self, ctx: RunContext) -> bool:
        t = ctx.state.transaction
        return bool(t and t.get("run_id") == ctx.run_id)

    def _commit(self, ctx: RunContext, log: logging.Logger) -> None:
        """rebuild + health passed: the promoted release is consistent end to end."""
        if self._own_txn(ctx):
            ctx.state.transaction = None
            save_state(self.cfg.paths.state_file, ctx.state)
            ctx.extras["committed"] = True
            log.info("release %s committed (rebuild + health passed)", ctx.run_id)

    # -- endings --------------------------------------------------------------
    def _finish(self, ctx: RunContext, status: str, code: int, result: str) -> int:
        ctx.state.last_run_id = ctx.run_id
        ctx.state.last_run_result = status
        save_state(self.cfg.paths.state_file, ctx.state)
        ctx.manifest.status, ctx.manifest.exit_code = status, code
        ctx.manifest.finished_utc, ctx.manifest.result = utc_iso(self.clock.now()), result
        ctx.manifest.save(ctx.workdir)
        return code

    def _mark_success(self, st: State) -> None:
        st.consecutive_failures = 0
        st.last_success_utc = utc_iso(self.clock.now())

    def _finish_nothing(self, ctx: RunContext, stage: Stage, res: StageResult) -> int:
        up = ctx.artifacts.get("upstream")
        if up:   # live data already matches these upstream versions
            ctx.state.scryfall_updated_at = up["scryfall"]["updated_at"]
            ctx.state.mtgish_sha = up["mtgish"]["sha"]
        self._mark_success(ctx.state)
        msg = f"nothing to do (stage {stage.name}): {res.summary}"
        _base(ctx.log).info("RESULT: %s", msg)
        return self._finish(ctx, "nothing_to_do", EXIT_OK, msg)

    def _finish_success(self, ctx: RunContext) -> int:
        log = _base(ctx.log)
        st = ctx.state
        for w in ctx.extras.get("warnings", []):
            log.warning("WARNING (non-fatal): %s", w)
        if "promoted" in ctx.artifacts:
            rel = ctx.artifacts["promoted"]
            if not ctx.extras.get("committed"):
                # Only reachable with stages.allow_partial_promote (config refuses it otherwise).
                if self._own_txn(ctx):
                    st.transaction = None
                log.warning("PARTIAL PROMOTION: release %s replaced the live files WITHOUT rebuild + health "
                            "(stages.allow_partial_promote). Postgres/API were not updated or checked.",
                            rel["release_id"])
                return self._finish(ctx, "partial", EXIT_OK, f"partially promoted {rel['release_id']}")
            up = ctx.artifacts["upstream"]
            st.scryfall_updated_at = up["scryfall"]["updated_at"]
            st.mtgish_sha = up["mtgish"]["sha"]
            self._mark_success(st)
            log.info("RESULT: PROMOTED release %s (%s cards; previous release kept as %s)",
                     rel["release_id"], f"{rel['cards_count']:,}", rel["backup_release_id"])
            for line in ctx.artifacts.get("content_diff", {}).get("summary", []):
                log.info("NEW CONTENT: %s", line)
            return self._finish(ctx, "success", EXIT_OK, f"promoted {rel['release_id']}")
        msg = (f"stages completed without promotion; candidate kept in {ctx.workdir} "
               f"(promote it with `run --resume {ctx.run_id}`)")
        log.info("RESULT: success (no promotion) - %s", msg)
        return self._finish(ctx, "partial", EXIT_OK, msg)

    def _finish_failed(self, ctx: RunContext, stage: Stage) -> int:
        log = _base(ctx.log)
        message = ctx.extras.get("failed_message", "")
        live = ctx.extras.get("live_outcome")
        if self._own_txn(ctx):
            live = self._revert(ctx, f"stage {stage.name} failed: {message}", log)
        elif live is None:
            live = ("live data unchanged" if not ctx.extras.get("live_touched")
                    else "live files were changed and reverted")
        st = ctx.state
        st.consecutive_failures += 1
        st.last_failure_utc = utc_iso(self.clock.now())
        st.last_failure_stage, st.last_failure_message = stage.name, message[:2000]
        log.error("RESULT: FAILED at stage %s (%s; %d consecutive failure(s)) - %s",
                  stage.name, live, st.consecutive_failures, message)
        return self._finish(ctx, "failed", EXIT_FAILED, f"failed at {stage.name}: {message[:500]}")

    def _recovery(self, ctx: RunContext, log: logging.Logger) -> Recovery:
        return Recovery(self.cfg, ctx.releases, ctx.services, log)

    def _revert(self, ctx: RunContext, reason: str, log: logging.Logger) -> str:
        target = (ctx.state.transaction or {}).get("restore_to")
        try:
            outcome = self._recovery(ctx, log).resolve(ctx.state, reason=reason, allow_rebuild=True)
        except RecoveryError as exc:
            log.critical("AUTOMATIC ROLLBACK FAILED - manual attention needed: %s. The open transaction stays "
                         "in state; `card_update recover` or the next run retries it.", exc)
            return f"AUTOMATIC ROLLBACK TO {target} FAILED - LIVE STATE UNRESOLVED"
        for rec in ctx.manifest.stages:
            if rec.name == "promote":
                rec.status = "rolled_back"
        ctx.artifacts.pop("promoted", None)
        return f"rolled back to {target}" + ("" if outcome == "resolved" else " (files only)")

    def _recover_open_transaction(self, ctx: RunContext) -> int:
        log = _base(ctx.log)
        t = ctx.state.transaction or {}
        reason = (f"{t.get('kind')} by {t.get('run_id')} at {t.get('started_utc')} never completed "
                  f"(phase {t.get('phase')}; crashed, killed or reverted files-only)")
        try:
            self._recovery(ctx, log).resolve(ctx.state, reason=reason, allow_rebuild=True)
            outcome = f"restored release {t.get('restore_to')}"
        except RecoveryError as exc:
            log.critical("RECOVERY FAILED - manual attention needed: %s", exc)
            outcome = f"recovery to {t.get('restore_to')} FAILED: {exc}"
        st = ctx.state
        st.consecutive_failures += 1
        st.last_failure_utc = utc_iso(self.clock.now())
        st.last_failure_stage, st.last_failure_message = "recovery", reason
        log.error("RESULT: FAILED - resolved an unfinished live change (%s); the next run starts clean", outcome)
        return self._finish(ctx, "failed", EXIT_FAILED, outcome)
