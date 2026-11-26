"""Injectable subprocess runner: streams child output into the run log (with secrets
redacted), keeps a tail for error messages, enforces a timeout.

Each child runs in its own process group (POSIX: new session). On timeout, SIGTERM or
any other interruption the WHOLE group is terminated and the runner waits until no
member is left, so no grandchild (e.g. load_to_postgres under rebuild_and_reload.sh)
can keep writing after the pipeline starts a rollback.

Child environments inherit os.environ (DATABASE_URL etc. from the systemd unit) plus
explicit extras. Environment values are never logged.
"""

from __future__ import annotations

import logging
import os
import re
import signal
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Mapping, Protocol, Sequence

_POSIX = os.name == "posix"
_REDACT = (
    (re.compile(r"(?i)(password\s*=\s*)('[^']*'|\"[^\"]*\"|\S+)"), r"\1***"),
    (re.compile(r"(?i)([a-z][a-z0-9+.-]*://[^:/@\s]+:)[^@\s]+@"), r"\1***@"),
)


def redact(line: str) -> str:
    """Mask password=... and user:password@ in a log line."""
    for rx, repl in _REDACT:
        line = rx.sub(repl, line)
    return line


class CommandTimeout(Exception):
    """The child exceeded its timeout and its process group was killed."""


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    duration_s: float
    tail: tuple[str, ...]

    def tail_text(self, n: int = 15) -> str:
        return "\n    ".join(self.tail[-n:]) or "(no output)"


class CommandRunner(Protocol):
    def run(self, argv: Sequence[str], *, cwd: Path, timeout_s: float, label: str,
            env: Mapping[str, str] | None = None) -> CommandResult: ...


def _group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:        # pragma: no cover - a member changed uid; treat as alive
        return True


def terminate_group(proc: subprocess.Popen, grace_s: float = 10.0, wait_s: float = 60.0) -> None:
    """TERM then KILL the child's whole process group and wait until it is empty."""
    if not _POSIX:                 # Windows dev box: no process groups to speak of
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        return
    pgid = proc.pid
    for sig, patience in ((signal.SIGTERM, grace_s), (signal.SIGKILL, wait_s)):
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            break
        deadline = time.monotonic() + patience
        while time.monotonic() < deadline:
            if proc.poll() is not None and not _group_alive(pgid):
                proc.wait()
                return
            time.sleep(0.2)
    proc.wait()
    if _group_alive(pgid):         # pragma: no cover - unkillable (D state)
        raise RuntimeError(f"process group {pgid} survived SIGKILL; refusing to continue")


class SubprocessRunner:
    def __init__(self, log: logging.Logger | logging.LoggerAdapter, tail_lines: int = 40) -> None:
        self.log = log
        self.tail_lines = tail_lines

    def run(self, argv: Sequence[str], *, cwd: Path, timeout_s: float, label: str,
            env: Mapping[str, str] | None = None) -> CommandResult:
        child_env = dict(os.environ)
        child_env.update({"PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"})
        if env:
            child_env.update(env)
        argv = tuple(str(a) for a in argv)
        self.log.info("[%s] $ %s  (cwd %s, timeout %.0fs)", label, redact(" ".join(argv)), cwd, timeout_s)
        tail: deque[str] = deque(maxlen=self.tail_lines)
        start = time.monotonic()
        group = {"start_new_session": True} if _POSIX else {
            "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}  # type: ignore[attr-defined]
        proc = subprocess.Popen(argv, cwd=str(cwd), env=child_env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, **group)
        assert proc.stdout is not None
        reader = threading.Thread(target=self._pump, args=(proc.stdout, label, tail), daemon=True)
        reader.start()
        try:
            rc = proc.wait(timeout=max(timeout_s, 0.001))
        except subprocess.TimeoutExpired:
            terminate_group(proc)
            reader.join(timeout=10)
            raise CommandTimeout(f"{label}: exceeded {timeout_s:.0f}s; its process group was killed; "
                                 "last output:\n    " + ("\n    ".join(list(tail)[-15:]) or "(none)")) from None
        except BaseException:          # SIGTERM/Ctrl-C while waiting: never orphan descendants
            terminate_group(proc)
            raise
        if _POSIX and _group_alive(proc.pid):
            self.log.warning("[%s] left processes behind in its group; terminating them", label)
            terminate_group(proc)
        reader.join(timeout=30)
        duration = time.monotonic() - start
        self.log.info("[%s] exit %d after %.1fs", label, rc, duration)
        return CommandResult(argv=argv, returncode=rc, duration_s=duration, tail=tuple(tail))

    def _pump(self, stream: IO[bytes], label: str, tail: deque[str]) -> None:
        for raw in iter(stream.readline, b""):
            line = redact(raw.decode("utf-8", errors="replace").rstrip("\r\n"))
            tail.append(line)
            self.log.info("[%s] %s", label, line)
        stream.close()
