"""Exclusive file lock shared with deploy/refresh_corpus.sh and deploy/deploy.sh.

Uses flock(2) (the same lock the `flock` utility takes), so shell jobs and this package
exclude each other. The file is opened read-only with O_CREAT: whoever creates it first
(root via deploy.sh, or simmander) the other can still open and lock it.
On Windows (dev box only) msvcrt byte-range locking stands in.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from types import TracebackType

from card_update.clock import Clock

try:  # pragma: no cover - platform dependent
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]
    import msvcrt


class LockTimeout(Exception):
    """The lock stayed held by another job for longer than the configured wait."""


class FileLock:
    def __init__(self, path: Path, wait_s: float, clock: Clock, poll_s: float = 5.0,
                 log: logging.Logger | logging.LoggerAdapter | None = None) -> None:
        self.path = Path(path)
        self.wait_s = wait_s
        self.poll_s = poll_s
        self.clock = clock
        self.log = log
        self._fd: int | None = None

    def _open(self) -> int:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if fcntl is not None:
            return os.open(str(self.path), os.O_RDONLY | os.O_CREAT, 0o664)
        return os.open(str(self.path), os.O_RDWR | os.O_CREAT, 0o664)

    def _try_lock(self, fd: int) -> bool:
        try:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:  # pragma: no cover - Windows dev box
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    def acquire(self) -> None:
        fd = self._open()
        start = self.clock.monotonic()
        announced = False
        while not self._try_lock(fd):
            waited = self.clock.monotonic() - start
            if waited >= self.wait_s:
                os.close(fd)
                raise LockTimeout(
                    f"lock {self.path} still held by another job after {waited:.0f}s "
                    f"(deckdoctor-refresh, deckdoctor-cardupdate or a deploy); not running")
            if not announced and self.log is not None:
                self.log.warning("lock %s is held by another job; waiting up to %.0fs",
                                 self.path, self.wait_s)
                announced = True
            self.clock.sleep(min(self.poll_s, max(self.wait_s - waited, 0.0)) or self.poll_s)
        self._fd = fd

    def release(self) -> None:
        if self._fd is None:
            return
        fd, self._fd = self._fd, None
        try:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_UN)
            else:  # pragma: no cover - Windows dev box
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        finally:
            os.close(fd)

    def __enter__(self) -> "FileLock":
        self.acquire()
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None,
                 tb: TracebackType | None) -> None:
        self.release()
