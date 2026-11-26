"""Card-layer releases: the live triple (cards.json, land_meta.json, scores.sqlite) and
backup snapshots of it under ``<card_data_dir>/releases/<release-id>/``.

* snapshot_live: copy the live files into a new release dir (SQLite via the backup API,
  so un-checkpointed WAL pages are included), written as ``.<id>.partial`` then renamed.
* install: move verified candidates over the live paths with os.replace (atomic per file;
  same filesystem, else copy+fsync+rename).
* restore: copy a release back over the live paths after re-checking its sha256s.

Live SQLite is checkpointed before it is replaced so no stale -wal can be replayed onto
the new file. Callers hold the pipeline lock: nothing else writes these files meanwhile.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from card_update.clock import Clock
from card_update.fsutil import (atomic_write_json, copy_file_atomic, free_bytes, fsync_dir, fsync_file,
                                move_into_place, sha256_file, utc_iso)
from card_update.snapshot import load_json_file

CARDS, LAND_META, SCORES = "cards.json", "land_meta.json", "scores.sqlite"
LIVE_NAMES = (CARDS, LAND_META, SCORES)
# scores first, cards last: the API reads cards.json, so it flips last.
INSTALL_ORDER = (SCORES, LAND_META, CARDS)
RELEASE_META = "release.json"
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class ReleaseError(Exception):
    pass


@dataclass(frozen=True)
class LivePaths:
    cards: Path
    land_meta: Path
    scores: Path

    def by_name(self) -> dict[str, Path]:
        return {CARDS: self.cards, LAND_META: self.land_meta, SCORES: self.scores}


@dataclass
class ReleaseInfo:
    release_id: str
    path: Path
    created_utc: str
    files: dict[str, dict[str, Any]] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)


def check_release_id(release_id: str) -> str:
    if not _ID_RE.match(release_id or ""):
        raise ReleaseError(f"invalid release id {release_id!r}")
    return release_id


def prepare_live_sqlite(path: Path) -> None:
    """Checkpoint the live store so no -wal/-shm sidecar outlives the file being replaced."""
    if not path.exists():
        return
    con = sqlite3.connect(str(path))
    try:
        busy, _, _ = con.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    finally:
        con.close()
    if busy:
        raise ReleaseError(f"{path}: WAL checkpoint blocked by another connection — is a "
                           "build or load running without the pipeline lock?")
    wal = Path(str(path) + "-wal")
    if wal.exists() and wal.stat().st_size:
        raise ReleaseError(f"{wal} still holds un-checkpointed data; refusing to replace {path}")
    for suffix in ("-wal", "-shm"):
        side = Path(str(path) + suffix)
        if side.exists():
            side.unlink()


def _sqlite_copy(src: Path, dst: Path) -> None:
    s = sqlite3.connect(f"{src.resolve().as_uri()}?mode=ro", uri=True)
    d = sqlite3.connect(str(dst))
    try:
        s.backup(d)
        d.execute("PRAGMA journal_mode=DELETE")
        d.commit()
    finally:
        d.close()
        s.close()
    fsync_file(dst)


class ReleaseStore:
    def __init__(self, releases_dir: Path, live: LivePaths, clock: Clock,
                 log: logging.Logger | logging.LoggerAdapter) -> None:
        self.dir = Path(releases_dir)
        self.live = live
        self.clock = clock
        self.log = log

    # ── queries ──────────────────────────────────────────────────────────────
    def get(self, release_id: str) -> ReleaseInfo:
        path = self.dir / check_release_id(release_id)
        meta, err = load_json_file(path / RELEASE_META)
        if err is not None or not isinstance(meta, dict):
            raise ReleaseError(f"release {release_id} not found or unreadable at {path} ({err})")
        return ReleaseInfo(release_id=release_id, path=path, created_utc=meta.get("created_utc", ""),
                           files=meta.get("files", {}), provenance=meta.get("provenance", {}))

    def list(self) -> list[ReleaseInfo]:
        if not self.dir.exists():
            return []
        out = []
        for p in self.dir.iterdir():
            if p.is_dir() and not p.name.startswith(".") and (p / RELEASE_META).exists():
                try:
                    out.append(self.get(p.name))
                except ReleaseError as exc:
                    self.log.warning("ignoring unreadable release dir %s: %s", p, exc)
        return sorted(out, key=lambda r: (r.created_utc, r.release_id), reverse=True)

    # ── mutations ────────────────────────────────────────────────────────────
    def snapshot_live(self, release_id: str, provenance: dict[str, Any]) -> ReleaseInfo:
        check_release_id(release_id)
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.dir / f".{release_id}.partial"
        if tmp.exists():
            shutil.rmtree(tmp)
        tmp.mkdir()
        files: dict[str, dict[str, Any]] = {}
        for name, live in self.live.by_name().items():
            if not live.exists():
                self.log.warning("snapshot %s: live %s does not exist; not in the release", release_id, live)
                continue
            dst = tmp / name
            if name == SCORES:
                _sqlite_copy(live, dst)
            else:
                shutil.copyfile(live, dst)
                fsync_file(dst)
            files[name] = {"sha256": sha256_file(dst), "size": dst.stat().st_size, "source": str(live)}
        if CARDS not in files:
            shutil.rmtree(tmp)
            raise ReleaseError(f"cannot snapshot: live cards file {self.live.cards} is missing")
        atomic_write_json(tmp / RELEASE_META, {"release_id": release_id, "created_utc": utc_iso(self.clock.now()),
                                               "files": files, "provenance": provenance})
        final = self.dir / release_id
        old = self.dir / f".{release_id}.old"
        if old.exists():
            shutil.rmtree(old)
        if final.exists():               # never delete the previous snapshot before the new one is in place
            os.replace(final, old)
        os.replace(tmp, final)
        fsync_dir(self.dir)
        if old.exists():
            shutil.rmtree(old)
        self.log.info("snapshot of live card layer saved as release %s (%s)", release_id,
                      ", ".join(f"{n} {f['size']:,} B" for n, f in files.items()))
        return self.get(release_id)

    def install(self, candidates: dict[str, Path]) -> None:
        unknown = set(candidates) - set(LIVE_NAMES)
        if unknown:
            raise ReleaseError(f"unknown candidate file(s): {sorted(unknown)}")
        live = self.live.by_name()
        for name in INSTALL_ORDER:
            if name not in candidates:
                continue
            src, dst = Path(candidates[name]), live[name]
            if not src.exists():
                raise ReleaseError(f"candidate {src} vanished before install")
            if name == SCORES:
                prepare_live_sqlite(dst)
            move_into_place(src, dst)
            self.log.info("installed %s -> %s", src.name, dst)

    def restore(self, release_id: str) -> ReleaseInfo:
        info = self.get(release_id)
        for name, meta in info.files.items():         # verify everything before touching live
            p = info.path / name
            if not p.exists() or sha256_file(p) != meta.get("sha256"):
                raise ReleaseError(f"release {release_id}: {name} is missing or does not match its "
                                   "recorded sha256 — refusing to restore from it")
        live = self.live.by_name()
        short = [f"{live[n].parent} needs {int(m['size']):,} B, has {free_bytes(live[n].parent):,} B"
                 for n, m in info.files.items() if free_bytes(live[n].parent) < int(m.get("size", 0)) + (64 << 20)]
        if short:
            raise ReleaseError("not enough free disk space to restore release "
                               f"{release_id} ({'; '.join(short)}) — free space (old run dirs under "
                               "card-data/runs are safe to delete) and run `card_update recover`")
        for name in INSTALL_ORDER:
            if name not in info.files:
                continue
            if name == SCORES:
                prepare_live_sqlite(live[name])
            copy_file_atomic(info.path / name, live[name])
            self.log.info("restored %s from release %s -> %s", name, release_id, live[name])
        return info

    def prune(self, keep: int, protect: set[str]) -> list[str]:
        removed = []
        for i, rel in enumerate(self.list()):
            if i < keep or rel.release_id in protect:
                continue
            shutil.rmtree(rel.path)
            removed.append(rel.release_id)
        for pattern in (".*.partial", ".*.old"):
            for p in self.dir.glob(pattern) if self.dir.exists() else []:
                shutil.rmtree(p)
        return removed
