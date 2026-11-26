"""Crash-safe changes to the live card layer.

Every change of the live files (promote, rollback) is a transaction recorded in
``state.transaction`` BEFORE the first live file changes, and cleared only when the
change is complete AND consistent with Postgres/API (after rebuild + health, or right
away when Postgres was never touched). Whoever finds a transaction open — the next run,
``card_update recover`` (also the API's ExecStartPre), ``rollback`` — resolves it the
same way: restore release ``restore_to`` (sha-verified), then, if Postgres may hold
other data (``needs_rebuild``), rebuild_and_reload + live verification.

    {"kind": "promote"|"rollback", "run_id", "restore_to", "needs_rebuild": bool,
     "phase": "installing"|"installed"|"rebuilding"|"files_restored", "started_utc"}
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from card_update.config import Config
from card_update.context import Services
from card_update.fsutil import atomic_write_json, sha256_file
from card_update.ops import OpsError, run_rebuild, verify_live
from card_update.releases import CARDS, LAND_META, ReleaseError, ReleaseStore
from card_update.snapshot import load_cards, load_json_file
from card_update.state import State, save_state

PROVENANCE = "PROVENANCE.json"
_HEAVY = ("*.jsonl.gz", "default-cards.json", "mtgish.lines.*.json", "scores*.sqlite", "cards.json")


class RecoveryError(Exception):
    pass


def live_provenance(cfg: Config, st: State) -> dict[str, Any]:
    """What the current live release was built from (stored with its backup snapshot)."""
    data, err = load_json_file(cfg.paths.live_cards.parent / PROVENANCE)
    base = data if isinstance(data, dict) and err is None else {}
    return {**base, "release_id": st.current_release_id, "scryfall_updated_at": st.scryfall_updated_at,
            "mtgish_sha": st.mtgish_sha, "cards_sha256": st.cards_sha256,
            "scoring_fingerprint": st.scoring_fingerprint,
            "unmapped_operators_sha256": st.unmapped_operators_sha256,
            "unmapped_operators": st.last_unmapped_operators}


def begin(cfg: Config, st: State, *, kind: str, run_id: str, restore_to: str, needs_rebuild: bool,
          now_utc: str, phase: str) -> None:
    if st.transaction:
        raise RecoveryError(f"another transaction is still open: {st.transaction}")
    st.transaction = {"kind": kind, "run_id": run_id, "restore_to": restore_to,
                      "needs_rebuild": needs_rebuild, "phase": phase, "started_utc": now_utc}
    save_state(cfg.paths.state_file, st)          # durable before any live file changes


def update(cfg: Config, st: State, **fields: Any) -> None:
    if st.transaction is None:
        raise RecoveryError("no open transaction to update")
    st.transaction.update(fields)
    save_state(cfg.paths.state_file, st)


class Recovery:
    def __init__(self, cfg: Config, releases: ReleaseStore, services: Services,
                 log: logging.Logger | logging.LoggerAdapter) -> None:
        self.cfg = cfg
        self.releases = releases
        self.services = services
        self.log = log

    # ── resolving an open transaction ───────────────────────────────────────
    def resolve(self, st: State, *, reason: str, allow_rebuild: bool = True) -> str:
        """Restore the transaction's ``restore_to`` release. Returns "resolved" (marker
        cleared) or "files-only" (files restored, marker kept: Postgres still needs a
        rebuild that allow_rebuild=False forbade)."""
        m = st.transaction
        if not m:
            return "resolved"
        target = str(m["restore_to"])
        log = self.log
        log.error("RESOLVING %s transaction of %s: restoring release %s — %s",
                  m.get("kind"), m.get("run_id"), target, reason)
        self._restore_files(st, target)
        update(self.cfg, st, phase="files_restored")
        if m.get("needs_rebuild"):
            if not allow_rebuild:
                log.error("files restored to %s; Postgres/API may still hold newer tables — transaction "
                          "kept open: the next run or `card_update recover` rebuilds and checks health", target)
                return "files-only"
            names = self.cfg.stages.order
            try:
                if "rebuild" in names:
                    run_rebuild(self.cfg, self.services.runner)
                if "health" in names:
                    verify_live(self.cfg, self.services.api, self.services.clock, log,
                                len(load_cards(Path(self.cfg.paths.live_cards))))
            except (OpsError, ValueError) as exc:
                raise RecoveryError(f"files restored to {target} but the live side is not healthy: {exc}") from None
        st.transaction = None
        save_state(self.cfg.paths.state_file, st)
        log.error("RESOLVED: release %s is live%s", target,
                  " and healthy" if m.get("needs_rebuild") and "health" in self.cfg.stages.order
                  else " (Postgres was not touched by the reverted change)")
        return "resolved"

    def _restore_files(self, st: State, target: str) -> None:
        try:
            try:
                info = self.releases.restore(target)
            except ReleaseError as exc:
                if "free disk space" not in str(exc):
                    raise
                self.log.error("%s — deleting heavy files of old run dirs and retrying", exc)
                self.free_run_space()
                info = self.releases.restore(target)
        except (ReleaseError, OSError) as exc:
            raise RecoveryError(f"could not restore release {target}: {exc}") from None
        prov = dict(info.provenance)
        atomic_write_json(self.cfg.paths.live_cards.parent / PROVENANCE, prov)
        st.current_release_id = target
        st.cards_sha256 = info.files[CARDS]["sha256"]
        if LAND_META in info.files:
            st.land_meta_sha256 = info.files[LAND_META]["sha256"]
        st.scryfall_updated_at = prov.get("scryfall_updated_at")
        st.mtgish_sha = prov.get("mtgish_sha")
        st.scoring_fingerprint = prov.get("scoring_fingerprint")
        st.unmapped_operators_sha256 = prov.get("unmapped_operators_sha256")
        st.last_unmapped_operators = prov.get("unmapped_operators")
        save_state(self.cfg.paths.state_file, st)

    def free_run_space(self) -> list[str]:
        """Delete re-downloadable / rebuildable files from run dirs (manifests and logs stay)."""
        removed = []
        runs = self.cfg.paths.runs_dir
        for pattern in _HEAVY:
            for p in runs.glob(f"*/{pattern}") if runs.exists() else []:
                p.unlink()
                removed.append(str(p))
        self.log.error("freed %d run-dir files", len(removed))
        return removed

    # ── manual rollback ─────────────────────────────────────────────────────
    def rollback(self, st: State, target: str, *, rebuild: bool, run_id: str, now_utc: str) -> str:
        if st.transaction:
            raise RecoveryError(f"an earlier change is unresolved ({st.transaction}); "
                                "run `card_update recover` first")
        self.releases.get(target)                         # exists + readable before touching anything
        cur = st.current_release_id
        if cur and cur != target:
            if st.cards_sha256 is None or sha256_file(self.cfg.paths.live_cards) == st.cards_sha256:
                self.releases.snapshot_live(cur, live_provenance(self.cfg, st))
            else:
                self.log.warning("live cards.json does not match release %s; not snapshotting it", cur)
        begin(self.cfg, st, kind="rollback", run_id=run_id, restore_to=target, needs_rebuild=True,
              now_utc=now_utc, phase="installing")
        return self.resolve(st, reason="manual rollback", allow_rebuild=rebuild)

