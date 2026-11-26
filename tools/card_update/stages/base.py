"""Stage contract. A stage does one job, is idempotent, reads its inputs from
``ctx.artifacts`` / config, writes only inside the run workdir (except promote/rebuild,
which own the live side), and reports what it did in a StageResult.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar

from card_update.context import RunContext


class Outcome(str, Enum):
    OK = "ok"
    NOTHING_TO_DO = "nothing_to_do"
    SKIPPED = "skipped"


class StageError(Exception):
    """The stage failed; the message says what broke and what to do."""


@dataclass
class StageResult:
    outcome: Outcome = Outcome.OK
    summary: str = ""
    outputs: dict[str, Any] = field(default_factory=dict)


class Stage:
    name: ClassVar[str] = ""
    # A non-fatal stage's failure is logged as a WARNING and the run continues (cleanup).
    # Any FATAL failure while this run's live transaction is open reverts the live side.
    fatal: ClassVar[bool] = True

    def describe(self, ctx: RunContext) -> str:
        raise NotImplementedError

    def run(self, ctx: RunContext) -> StageResult:
        raise NotImplementedError
