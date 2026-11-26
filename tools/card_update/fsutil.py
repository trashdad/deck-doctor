"""Atomic file helpers: every write goes tmp -> fsync -> os.replace (+ dir fsync)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_CHUNK = 1 << 20


def utc_iso(dt: datetime) -> str:
    """ISO-8601 UTC with a Z suffix, second precision."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc_iso(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def fsync_dir(path: Path) -> None:
    """Persist a rename. Directories cannot be opened on Windows; there it is a no-op."""
    if os.name != "posix":
        return
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _tmp_in(dirpath: Path, name: str) -> Path:
    fd, tmp = tempfile.mkstemp(prefix=f".{name}.", suffix=".tmp", dir=str(dirpath))
    os.close(fd)
    return Path(tmp)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp_in(path.parent, path.name)
    try:
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    fsync_dir(path.parent)


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_json(path: Path, obj: Any, indent: int | None = 2) -> None:
    atomic_write_text(path, json.dumps(obj, indent=indent, ensure_ascii=False, sort_keys=False) + "\n")


def fsync_file(path: Path) -> None:
    with open(path, "rb+") as fh:
        os.fsync(fh.fileno())


def copy_file_atomic(src: Path, dst: Path) -> None:
    """Copy src over dst so readers only ever see the old or the complete new file."""
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp_in(dst.parent, dst.name)
    try:
        shutil.copyfile(src, tmp)
        fsync_file(tmp)
        os.replace(tmp, dst)
    finally:
        if tmp.exists():
            tmp.unlink()
    fsync_dir(dst.parent)


def move_into_place(src: Path, dst: Path) -> None:
    """os.replace when src and dst share a filesystem, else copy atomically then delete src."""
    src, dst = Path(src), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if os.stat(src).st_dev == os.stat(dst.parent).st_dev:
        fsync_file(src)                 # data durable BEFORE the rename makes it visible
        os.replace(src, dst)
        fsync_dir(dst.parent)
    else:
        copy_file_atomic(src, dst)
        src.unlink()


def free_bytes(path: Path) -> int:
    probe = Path(path)
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return shutil.disk_usage(probe).free
