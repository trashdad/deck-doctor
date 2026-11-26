"""Stage 1 — is there anything new upstream (Scryfall bulk updated_at, MTGish commit)?"""

from __future__ import annotations

from card_update.context import RunContext
from card_update.stages.base import Outcome, Stage, StageError, StageResult
from card_update.upstream import UpstreamError, probe_upstream, upstream_changes


class CheckStage(Stage):
    name = "check"

    def describe(self, ctx: RunContext) -> str:
        return (f"GET {ctx.config.upstream.scryfall_bulk_url} and the MTGish commit "
                f"({'pinned ' + ctx.config.upstream.mtgish_pin_sha if ctx.config.upstream.mtgish_pin_sha else ctx.config.upstream.mtgish_head_url}); "
                "compare with state; stop with nothing-to-do if neither changed")

    def run(self, ctx: RunContext) -> StageResult:
        try:
            up = probe_upstream(ctx.config, ctx.services.fetcher)
        except UpstreamError as exc:
            raise StageError(f"upstream check failed: {exc}") from None
        ctx.artifacts["upstream"] = up
        changes = upstream_changes(ctx.state, up)
        outputs = {"scryfall_updated_at": up["scryfall"]["updated_at"], "mtgish_sha": up["mtgish"]["sha"],
                   "changes": changes}
        if not changes and not ctx.options.force:
            return StageResult(Outcome.NOTHING_TO_DO, "upstream unchanged since the live release "
                               f"(scryfall {up['scryfall']['updated_at']}, mtgish {up['mtgish']['sha'][:12]})",
                               outputs)
        why = "; ".join(changes) if changes else "no upstream change, continuing because of --force"
        return StageResult(Outcome.OK, why, outputs)
