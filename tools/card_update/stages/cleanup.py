"""Stage 11 — retention: keep the newest N backup releases, M run dirs, K days of logs."""

from __future__ import annotations

from card_update.context import RunContext
from card_update.retention import apply_retention
from card_update.stages.base import Stage, StageError, StageResult


class CleanupStage(Stage):
    name = "cleanup"
    fatal = False          # retention problems never undo a healthy release

    def describe(self, ctx: RunContext) -> str:
        r = ctx.config.retention
        return (f"keep {r.keep_releases} backup releases, {r.keep_runs} run dirs, "
                f"{r.keep_log_days} days of logs (current/backup releases always kept)")

    def run(self, ctx: RunContext) -> StageResult:
        try:
            removed = apply_retention(ctx.config, ctx.state, ctx.releases, ctx.services.clock, ctx.log, ctx.run_id)
        except OSError as exc:
            raise StageError(f"retention failed: {exc}") from None
        return StageResult(summary=", ".join(f"{len(v)} {k}" for k, v in removed.items()) + " removed",
                           outputs=removed)
