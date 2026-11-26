"""Stage 10 — live verification after rebuild: card_relationships / engines /
card_cooccurrence present and not collapsed vs before the release, and GET /health with
status ok, scores_loaded, exactly the candidate's card count, engines > 0 and no
collapsed counters. The pipeline commits the release only after this passes; a failure
reverts it (files + rebuild_and_reload + health) and exits 1."""

from __future__ import annotations

from card_update.context import RunContext
from card_update.ops import OpsError, verify_live
from card_update.stages.base import Stage, StageError, StageResult


class HealthStage(Stage):
    name = "health"

    def describe(self, ctx: RunContext) -> str:
        return (f"check rebuilt tables, then GET {ctx.config.health.api_base}/health until status ok, cards == "
                f"candidate count, engines > 0 (timeout {ctx.config.health.timeout_s:.0f}s)")

    def run(self, ctx: RunContext) -> StageResult:
        expected = ctx.require("verified")["cards_count"]
        try:
            live = verify_live(ctx.config, ctx.services.api, ctx.services.clock, ctx.log, expected,
                               ctx.artifacts.get("pre_promote"))
        except OpsError as exc:
            raise StageError(str(exc)) from None
        return StageResult(summary=f"live side healthy with {expected:,} cards", outputs=live)
