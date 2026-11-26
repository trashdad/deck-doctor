"""Command line: run | check | status | recover | rollback | gc | init.

    PYTHONPATH=tools python -m card_update [--config PATH] <command> [options]
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
from typing import IO, Any, Callable, Mapping, Sequence

from card_update.clock import Clock, SystemClock
from card_update.config import Config, ConfigError, load_config
from card_update.context import RunOptions, Services
from card_update.fingerprint import UNKNOWN, scoring_fingerprint
from card_update.fsutil import copy_file_atomic, parse_utc_iso, sha256_file, utc_iso
from card_update.http import UrllibFetcher
from card_update.lock import FileLock, LockTimeout
from card_update.logging_setup import close_logger, make_run_logger
from card_update.pipeline import (EXIT_FAILED, EXIT_LOCKED, EXIT_OK, EXIT_USAGE, Pipeline,
                                  live_paths)
from card_update.procs import SubprocessRunner
from card_update.releases import ReleaseError, ReleaseStore
from card_update.repo_bridge import FileRepoBridge
from card_update.retention import apply_retention
from card_update.state import StateError, load_state, save_state
from card_update.txn import Recovery, RecoveryError
from card_update.upstream import UpstreamError, probe_upstream, upstream_changes

ServicesFactoryBuilder = Callable[[Config, Clock], Callable[[logging.Logger], Services]]


class Terminated(Exception):
    """SIGTERM (systemd stop/timeout): unwinds like any failure, incl. the automatic revert."""


def default_services(cfg: Config, clock: Clock) -> Callable[[logging.Logger], Services]:
    def build(log: logging.Logger) -> Services:
        runner = SubprocessRunner(log)
        h = cfg.http
        fetcher = UrllibFetcher(user_agent=cfg.upstream.user_agent, timeout_s=h.timeout_s, retries=h.retries,
                                backoff_s=h.backoff_s, backoff_max_s=h.backoff_max_s,
                                min_interval_s=h.min_interval_s, clock=clock, log=log,
                                allowed_hosts=h.allowed_hosts, max_json_bytes=h.max_json_bytes)
        # Local API (loopback, http): no allowlist, no retries — health polls itself.
        api = UrllibFetcher(user_agent=cfg.upstream.user_agent, timeout_s=15, retries=0, backoff_s=0,
                            backoff_max_s=0, min_interval_s=0, clock=clock, log=log,
                            max_json_bytes=h.max_json_bytes)
        bridge = FileRepoBridge(cfg.paths.app_dir, cfg.paths.python, runner)
        return Services(fetcher=fetcher, api=api, runner=runner, clock=clock, bridge=bridge)
    return build


def _stage_list(values: Sequence[str] | None) -> tuple[str, ...]:
    out: list[str] = []
    for v in values or ():
        out.extend(x.strip() for x in v.split(",") if x.strip())
    return tuple(out)


def build_parser() -> argparse.ArgumentParser:
    help_ = "JSON config file (default: built-in defaults + env overrides)"
    # Accepted before or after the command; SUPPRESS keeps the subparser from resetting it.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default=argparse.SUPPRESS, help=help_)
    ap = argparse.ArgumentParser(prog="card_update",
                                 description="Deck Doctor automated card-data update pipeline.")
    ap.add_argument("--config", default=None, help=help_)
    sub = ap.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", parents=[common], help="full pipeline (default for the timer)")
    run.add_argument("--only", action="append", help="run only these stages (comma-separated)")
    run.add_argument("--skip", action="append", help="skip these stages (comma-separated)")
    run.add_argument("--from-stage", help="start at this stage (with --resume)")
    run.add_argument("--resume", metavar="RUN_ID", help="continue a failed/unfinished run in its own directory")
    run.add_argument("--dry-run", action="store_true", help="log what each stage would do; no side effects")
    run.add_argument("--no-promote", action="store_true", help="build + verify only; keep the candidate")
    run.add_argument("--force", action="store_true", help="continue even if upstream/cards are unchanged")
    run.add_argument("--waive", action="append", metavar="GATE",
                     help="log this gate's violations as WAIVED instead of failing (manual runs only)")

    sub.add_parser("check", parents=[common], help="is there anything new upstream? (exit 0 either way)")
    status = sub.add_parser("status", parents=[common], help="health of the job; exit 1 if stale/unresolved")
    status.add_argument("--offline", action="store_true", help="do not query upstream")
    rec = sub.add_parser("recover", parents=[common],
                         help="resolve an unfinished promote/rollback (exit 0 if nothing to do)")
    rec.add_argument("--files-only", action="store_true",
                     help="restore files only, never wait for the lock (the API's ExecStartPre)")
    rb = sub.add_parser("rollback", parents=[common], help="restore the previous card release")
    rb.add_argument("--to", metavar="RELEASE_ID", help="release to restore (default: newest backup)")
    rb.add_argument("--no-rebuild", action="store_true",
                    help="restore files only; the change stays open until a rebuild (next run / recover)")
    sub.add_parser("gc", parents=[common], help="apply retention to runs, releases and logs")
    init = sub.add_parser("init", parents=[common],
                          help="one-time: seed the live card dir from the tracked data/cards.json")
    init.add_argument("--mtgish-sha", help="MTGish commit the seeded store was built from")
    init.add_argument("--scryfall-updated-at", help="Scryfall bulk updated_at the seed was built from")
    base = init.add_mutually_exclusive_group()
    base.add_argument("--baseline-from-store", action="store_true",
                      help="the live store was built by unrecorded scoring code: the first run reports IER "
                           "drift as a warning instead of blocking, then records the real fingerprint")
    base.add_argument("--scoring-code-current", action="store_true",
                      help="the live store was built by the scoring code in this checkout: enforce the IER "
                           "gate from the first run")
    return ap


class _SigtermOnce:
    """First SIGTERM raises Terminated (run unwinds, reverting an open live change);
    later ones are logged and ignored so the revert can finish (systemd TimeoutStopSec
    bounds it)."""

    def __init__(self, out: IO[str]) -> None:
        self.out = out
        self.fired = False

    def __call__(self, signum: int, _frame: Any) -> None:
        if self.fired:
            print("SIGTERM again: ignored while the run unwinds/reverts", file=self.out, flush=True)
            return
        self.fired = True
        raise Terminated(f"terminated by signal {signum}")


def main(argv: Sequence[str] | None = None, *, environ: Mapping[str, str] | None = None,
         clock: Clock | None = None, services: ServicesFactoryBuilder = default_services,
         stream: IO[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:          # argparse: usage errors exit 2, --help exits 0
        return int(exc.code or 0)
    if stream is None and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")   # card names never crash logging
    out = stream or sys.stdout
    try:
        cfg = load_config(args.config, environ)
    except ConfigError as exc:
        print(f"config error: {exc}", file=out)
        return EXIT_USAGE
    clock = clock or SystemClock()
    factory = services(cfg, clock)
    handler = {"run": _cmd_run, "check": _cmd_check, "status": _cmd_status, "recover": _cmd_recover,
               "rollback": _cmd_rollback, "gc": _cmd_gc, "init": _cmd_init}[args.command]
    previous: Any = None
    try:
        previous = signal.signal(signal.SIGTERM, _SigtermOnce(out))
    except ValueError:                 # not the main thread (tests)
        previous = None
    try:
        return handler(args, cfg, clock, factory, out)
    finally:
        if previous is not None:
            signal.signal(signal.SIGTERM, previous)


# ── commands ────────────────────────────────────────────────────────────────

def _cmd_run(args: argparse.Namespace, cfg: Config, clock: Clock, factory, out: IO[str]) -> int:
    opts = RunOptions(only=_stage_list(args.only), skip=_stage_list(args.skip), from_stage=args.from_stage,
                      resume=args.resume, dry_run=args.dry_run, no_promote=args.no_promote,
                      force=args.force, waive=_stage_list(args.waive))
    try:
        pipeline = Pipeline(cfg, clock, factory, stream=out)
    except ConfigError as exc:
        print(f"config error: {exc}", file=out)
        return EXIT_USAGE
    return pipeline.run(opts)


def _cmd_check(args: argparse.Namespace, cfg: Config, clock: Clock, factory, out: IO[str]) -> int:
    log = make_run_logger("check", None, stream=out)
    try:
        state = load_state(cfg.paths.state_file)
        up = probe_upstream(cfg, factory(log).fetcher)
    except (StateError, UpstreamError) as exc:
        log.error("check failed: %s", exc)
        return EXIT_FAILED
    finally:
        close_logger(log)
    changes = upstream_changes(state, up)
    print("UPDATE AVAILABLE: " + "; ".join(changes) if changes else
          f"NOTHING NEW: scryfall {up['scryfall']['updated_at']}, mtgish {up['mtgish']['sha'][:12]}", file=out)
    return EXIT_OK


def _age_days(clock: Clock, stamp: str | None) -> float | None:
    if not stamp:
        return None
    return (clock.now() - parse_utc_iso(stamp)).total_seconds() / 86400


def _cmd_status(args: argparse.Namespace, cfg: Config, clock: Clock, factory, out: IO[str]) -> int:
    try:
        st = load_state(cfg.paths.state_file)
    except StateError as exc:
        print(f"STATE UNREADABLE: {exc}", file=out)
        return EXIT_FAILED
    age = _age_days(clock, st.last_success_utc)
    stale = age is None or age > cfg.status.stale_after_days
    lines = [
        f"current release:       {st.current_release_id or 'none (run init)'}",
        f"last success:          {st.last_success_utc or 'never'}"
        + (f" ({age:.1f} days ago)" if age is not None else ""),
        f"consecutive failures:  {st.consecutive_failures}"
        + (f" (last: {st.last_failure_stage} at {st.last_failure_utc}: {(st.last_failure_message or '')[:200]})"
           if st.consecutive_failures else ""),
        f"last run:              {st.last_run_id or '-'} ({st.last_run_result or '-'})",
        f"live upstream:         scryfall {st.scryfall_updated_at or '?'}, mtgish {(st.mtgish_sha or '?')[:12]}",
        f"scoring fingerprint:   {(st.scoring_fingerprint or 'none recorded')[:12]}"
        f" (code now {scoring_fingerprint(cfg.paths.app_dir)[:12]})",
    ]
    if st.transaction:
        lines.append(f"UNRESOLVED CHANGE:     {st.transaction} (run `card_update recover`; the next run does it)")
    if not args.offline:
        log = make_run_logger("status", None, stream=out)
        try:
            changes = upstream_changes(st, probe_upstream(cfg, factory(log).fetcher))
            lines.append("pending upstream:      " + ("; ".join(changes) if changes else "none"))
        except UpstreamError as exc:
            lines.append(f"pending upstream:      UNKNOWN ({exc})")
        finally:
            close_logger(log)
    lines.append(f"verdict:               {'STALE' if stale else 'OK'} (stale after "
                 f"{cfg.status.stale_after_days:g} days without a successful run)")
    print("\n".join(lines), file=out)
    return EXIT_FAILED if stale or st.transaction else EXIT_OK


def _lock(cfg: Config, clock: Clock, log: logging.Logger, wait: bool = True) -> FileLock:
    lock = FileLock(cfg.paths.lock_file, wait_s=cfg.lock.wait_minutes * 60 if wait else 0, clock=clock, log=log)
    lock.acquire()
    return lock


def _locked(cfg: Config, clock: Clock, log: logging.Logger, fn: Callable[[], int]) -> int:
    try:
        lock = _lock(cfg, clock, log)
    except LockTimeout as exc:
        log.error("%s", exc)
        return EXIT_LOCKED
    try:
        return fn()
    finally:
        lock.release()


def _cmd_recover(args: argparse.Namespace, cfg: Config, clock: Clock, factory, out: IO[str]) -> int:
    run_id = "recover-" + clock.now().strftime("%Y%m%dT%H%M%SZ")
    log = make_run_logger(run_id, None, stream=out)
    try:
        try:
            st = load_state(cfg.paths.state_file)
        except StateError as exc:
            log.error("RECOVER: %s", exc)
            return EXIT_FAILED
        if not st.transaction:
            log.info("recover: no unfinished live change; nothing to do")
            return EXIT_OK
        try:
            lock = _lock(cfg, clock, log, wait=not args.files_only)
        except LockTimeout:
            if args.files_only:
                log.warning("recover: a data job holds %s and owns the open change %s; not touching it",
                            cfg.paths.lock_file, st.transaction)
                return EXIT_OK
            log.error("recover: lock %s still held after %.0f min", cfg.paths.lock_file, cfg.lock.wait_minutes)
            return EXIT_LOCKED
        try:
            st = load_state(cfg.paths.state_file)            # re-read under the lock
            if not st.transaction:
                log.info("recover: resolved meanwhile; nothing to do")
                return EXIT_OK
            releases = ReleaseStore(cfg.paths.releases_dir, live_paths(cfg), clock, log)
            outcome = Recovery(cfg, releases, factory(log), log).resolve(
                st, reason="recover command" + (" (API start, files only)" if args.files_only else ""),
                allow_rebuild=not args.files_only)
            log.error("RECOVER: %s", outcome)
            return EXIT_OK
        except (RecoveryError, StateError) as exc:
            log.critical("RECOVER FAILED: %s", exc)
            return EXIT_FAILED
        finally:
            lock.release()
    finally:
        close_logger(log)


def _cmd_rollback(args: argparse.Namespace, cfg: Config, clock: Clock, factory, out: IO[str]) -> int:
    run_id = "rollback-" + clock.now().strftime("%Y%m%dT%H%M%SZ")
    log = make_run_logger(run_id, cfg.paths.logs_dir / f"{run_id}.log", stream=out)

    def do() -> int:
        st = load_state(cfg.paths.state_file)
        releases = ReleaseStore(cfg.paths.releases_dir, live_paths(cfg), clock, log)
        recovery = Recovery(cfg, releases, factory(log), log)
        if st.transaction:
            log.error("an unfinished live change is open (%s); resolving it instead — rerun rollback "
                      "afterwards if you still want another release", st.transaction)
            recovery.resolve(st, reason="rollback command found an open change", allow_rebuild=not args.no_rebuild)
            return EXIT_OK
        target = args.to or next(
            (r.release_id for r in releases.list() if r.release_id != st.current_release_id), None)
        if not target:
            log.error("no backup release to roll back to (releases dir %s)", cfg.paths.releases_dir)
            return EXIT_FAILED
        outcome = recovery.rollback(st, target, rebuild=not args.no_rebuild, run_id=run_id,
                                    now_utc=utc_iso(clock.now()))
        if outcome != "resolved":
            log.warning("files restored; Postgres not rebuilt (--no-rebuild): the change stays open until "
                        "`card_update recover` or the next run rebuilds it")
        log.warning("the daily timer will re-promote newer upstream data; to hold this release run "
                    "`systemctl disable --now deckdoctor-cardupdate.timer` until fixed")
        return EXIT_OK

    try:
        return _locked(cfg, clock, log, do)
    except (StateError, RecoveryError, ReleaseError) as exc:
        log.critical("ROLLBACK FAILED: %s", exc)
        return EXIT_FAILED
    finally:
        close_logger(log)


def _cmd_gc(args: argparse.Namespace, cfg: Config, clock: Clock, factory, out: IO[str]) -> int:
    log = make_run_logger("gc", None, stream=out)

    def do() -> int:
        st = load_state(cfg.paths.state_file)
        releases = ReleaseStore(cfg.paths.releases_dir, live_paths(cfg), clock, log)
        removed = apply_retention(cfg, st, releases, clock, log, None)
        log.info("gc done: %s", {k: len(v) for k, v in removed.items()})
        return EXIT_OK

    try:
        return _locked(cfg, clock, log, do)
    except (StateError, OSError) as exc:
        log.error("gc failed: %s", exc)
        return EXIT_FAILED
    finally:
        close_logger(log)


def _cmd_init(args: argparse.Namespace, cfg: Config, clock: Clock, factory, out: IO[str]) -> int:
    log = make_run_logger("init", None, stream=out)
    p = cfg.paths

    def do() -> int:
        st = load_state(p.state_file)
        if p.live_cards.exists():
            log.info("already initialised: %s exists (release %s); nothing to do", p.live_cards,
                     st.current_release_id)
            return EXIT_OK
        if not p.seed_cards.exists():
            log.error("seed cards file %s missing", p.seed_cards)
            return EXIT_FAILED
        sha = args.mtgish_sha
        if sha and (len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha)):
            log.error("--mtgish-sha must be a full 40-hex commit sha")
            return EXIT_USAGE
        copy_file_atomic(p.seed_cards, p.live_cards)
        if p.seed_land_meta.exists() and not p.live_land_meta.exists():
            copy_file_atomic(p.seed_land_meta, p.live_land_meta)
        st.cards_sha256 = sha256_file(p.live_cards)
        st.land_meta_sha256 = sha256_file(p.live_land_meta) if p.live_land_meta.exists() else None
        st.current_release_id = f"seed-{st.cards_sha256[:12]}"
        st.mtgish_sha = sha or st.mtgish_sha
        st.scryfall_updated_at = args.scryfall_updated_at or st.scryfall_updated_at
        if args.baseline_from_store:
            st.scoring_fingerprint = UNKNOWN
        elif args.scoring_code_current:
            st.scoring_fingerprint = scoring_fingerprint(p.app_dir)
        st.last_success_utc = st.last_success_utc or utc_iso(clock.now())
        save_state(p.state_file, st)
        log.info("seeded %s and %s from the tracked copies (release %s, scoring fingerprint %s). Now point "
                 "the API at them: SIMMANDER_CARDS=%s SIMMANDER_LAND_META=%s", p.live_cards, p.live_land_meta,
                 st.current_release_id, st.scoring_fingerprint or "none (IER gate enforced on the first run)",
                 p.live_cards, p.live_land_meta)
        return EXIT_OK

    try:
        return _locked(cfg, clock, log, do)
    except StateError as exc:
        log.error("%s", exc)
        return EXIT_FAILED
    finally:
        close_logger(log)
