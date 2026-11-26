"""Stage 9 — deploy/rebuild_and_reload.sh: relationships + co-occurrence on the new
store, load Postgres, hot-reload the API. Failure -> automatic rollback."""

from __future__ import annotations

from card_update import txn
from card_update.context import RunContext
from card_update.ops import OpsError, run_rebuild
from card_update.stages.base import Stage, StageError, StageResult


class RebuildStage(Stage):
    name = "rebuild"

    def describe(self, ctx: RunContext) -> str:
        return (f"{ctx.config.rebuild.bash} {ctx.config.rebuild.script} (build_relationships, build_cooccurrence, "
                f"load_to_postgres, POST {ctx.config.health.api_base}/admin/reload)")

    def run(self, ctx: RunContext) -> StageResult:
        if ctx.state.transaction and ctx.state.transaction.get("run_id") == ctx.run_id:
            # From here on Postgres may hold the new tables: a revert must rebuild too.
            txn.update(ctx.config, ctx.state, needs_rebuild=True, phase="rebuilding")
        try:
            res = run_rebuild(ctx.config, ctx.services.runner, ctx.child_timeout(ctx.config.rebuild.timeout_minutes * 60))
        except OpsError as exc:
            raise StageError(str(exc)) from None
        return StageResult(summary=f"rebuilt and reloaded in {res.duration_s:.0f}s",
                           outputs={"duration_s": round(res.duration_s, 1)})
