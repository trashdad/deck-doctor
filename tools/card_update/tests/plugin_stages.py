"""A plugged-in stage for test_pipeline (stages.order entry 'plugin_stages:BoomStage')."""

from card_update.stages.base import Stage


class BoomStage(Stage):
    name = "boom"

    def describe(self, ctx):
        return "raise to prove unexpected errors fail the run cleanly"

    def run(self, ctx):
        raise RuntimeError("boom")


class ClockJumpStage(Stage):
    """Pretends a stage took 13 hours (FakeClock), to trip run.deadline_hours."""
    name = "clockjump"

    def describe(self, ctx):
        return "advance the fake clock by 13 h"

    def run(self, ctx):
        from card_update.stages.base import StageResult
        ctx.services.clock.advance(13 * 3600)
        return StageResult(summary="13 h later")
