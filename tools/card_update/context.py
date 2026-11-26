"""Per-run context handed to every stage (no module-level mutable state)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from card_update.clock import Clock
from card_update.config import Config
from card_update.http import Fetcher
from card_update.manifest import Manifest
from card_update.procs import CommandRunner
from card_update.releases import ReleaseStore
from card_update.repo_bridge import RepoBridge
from card_update.state import State, save_state


@dataclass(frozen=True)
class RunOptions:
    only: tuple[str, ...] = ()
    skip: tuple[str, ...] = ()
    from_stage: str | None = None
    resume: str | None = None
    dry_run: bool = False
    no_promote: bool = False
    force: bool = False
    waive: tuple[str, ...] = ()


@dataclass
class Services:
    fetcher: Fetcher            # upstream (Scryfall, GitHub): retries + backoff
    api: Fetcher                # local Deck Doctor API (health): no retries, polled
    runner: CommandRunner
    clock: Clock
    bridge: RepoBridge


class MissingInput(Exception):
    """A stage needs an artifact an earlier stage did not produce in this run."""


class DeadlineExceeded(Exception):
    """The run used up run.deadline_hours."""


# Which stage produces which artifact (for actionable "missing input" errors).
PRODUCERS: Mapping[str, str] = MappingProxyType({
    "upstream": "check", "downloads": "fetch", "candidate": "prep",
    "verified": "verify", "promoted": "promote",
})


@dataclass
class RunContext:
    config: Config
    run_id: str
    workdir: Path
    state: State
    manifest: Manifest
    services: Services
    options: RunOptions
    log: logging.Logger | logging.LoggerAdapter
    releases: ReleaseStore
    extras: dict[str, Any] = field(default_factory=dict)
    deadline: float | None = None        # clock.monotonic() value the whole run must end by

    def remaining_s(self) -> float | None:
        return None if self.deadline is None else self.deadline - self.services.clock.monotonic()

    def child_timeout(self, seconds: float) -> float:
        """A child's timeout, capped to what is left of the run deadline."""
        left = self.remaining_s()
        if left is not None and left <= 0:
            raise DeadlineExceeded("run deadline (run.deadline_hours) exceeded")
        return seconds if left is None else max(1.0, min(seconds, left))

    @property
    def artifacts(self) -> dict[str, Any]:
        return self.manifest.artifacts

    def require(self, key: str) -> Any:
        if key not in self.artifacts:
            producer = PRODUCERS.get(key, "?")
            raise MissingInput(
                f"missing input '{key}' (produced by stage '{producer}' in the same run): run that "
                f"stage first, or `run --resume <run-id>` a run that already has it")
        return self.artifacts[key]

    def save_state(self) -> None:
        save_state(self.config.paths.state_file, self.state)
