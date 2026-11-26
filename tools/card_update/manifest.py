"""Run manifest: one JSON per run (inputs, outputs, timings, status per stage, plus the
artifacts later stages consume). Rewritten atomically after every stage, so a crashed
run can be inspected and resumed (``run --resume <run-id>``).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from card_update.fsutil import atomic_write_json

MANIFEST_NAME = "manifest.json"


class ManifestError(Exception):
    pass


@dataclass
class StageRecord:
    name: str
    status: str                       # ok | nothing_to_do | skipped | failed | dry_run
    started_utc: str | None = None
    ended_utc: str | None = None
    duration_s: float | None = None
    summary: str = ""
    outputs: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class Manifest:
    run_id: str
    workdir: str
    created_utc: str
    options: dict[str, Any] = field(default_factory=dict)
    stages: list[StageRecord] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
    status: str = "running"           # running | success | nothing_to_do | partial | failed
    exit_code: int | None = None
    finished_utc: str | None = None
    result: str = ""

    def record(self, rec: StageRecord) -> None:
        self.stages = [s for s in self.stages if s.name != rec.name] + [rec]

    def stage_status(self, name: str) -> str | None:
        for s in self.stages:
            if s.name == name:
                return s.status
        return None

    def save(self, workdir: Path) -> None:
        atomic_write_json(Path(workdir) / MANIFEST_NAME, asdict(self))


def load_manifest(workdir: Path) -> Manifest:
    path = Path(workdir) / MANIFEST_NAME
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        stages = [StageRecord(**s) for s in raw.pop("stages", [])]
        return Manifest(stages=stages, **raw)
    except FileNotFoundError:
        raise ManifestError(f"no run manifest at {path}") from None
    except (OSError, ValueError, TypeError) as exc:
        raise ManifestError(f"unreadable run manifest {path}: {exc}") from None
