"""Stage 7 — OPTIONAL manual approval (approve.enabled, default false).

When enabled the run fails (alerting) until ``<approvals_dir>/<run-id>.approved`` exists;
then ``run --resume <run-id>`` continues from here.
"""

from __future__ import annotations

from card_update.context import RunContext
from card_update.fsutil import utc_iso
from card_update.stages.base import Outcome, Stage, StageError, StageResult


class ApproveStage(Stage):
    name = "approve"

    def _file(self, ctx: RunContext):
        return ctx.config.paths.approvals_dir / f"{ctx.run_id}.approved"

    def describe(self, ctx: RunContext) -> str:
        if not ctx.config.approve.enabled:
            return "manual approval disabled (approve.enabled=false): pass through"
        return f"wait for {self._file(ctx)} (up to {ctx.config.approve.wait_minutes} min), else fail"

    def run(self, ctx: RunContext) -> StageResult:
        if not ctx.config.approve.enabled:
            return StageResult(Outcome.SKIPPED, "manual approval disabled (approve.enabled=false)")
        path = self._file(ctx)
        deadline = ctx.services.clock.monotonic() + ctx.config.approve.wait_minutes * 60
        while not path.exists():
            if ctx.services.clock.monotonic() >= deadline:
                raise StageError(
                    f"awaiting manual approval of run {ctx.run_id}. Review its log/manifest in {ctx.workdir}, "
                    f"then: touch {path} && PYTHONPATH=tools python -m card_update run --resume {ctx.run_id}")
            ctx.services.clock.sleep(30)
        return StageResult(summary=f"approved via {path}",
                           outputs={"approval_file": str(path), "checked_utc": utc_iso(ctx.services.clock.now())})
