"""Stage 8 — transactional promotion.

1. refuse if live cards.json is not the recorded release (mixed/unknown live state);
2. record the pre-promote baseline (rebuilt-table row counts, /health counters);
3. snapshot the live triple as backup release ``<current release id>``;
4. open the durable transaction (state.transaction, restore_to = backup) — BEFORE any
   live file changes;
5. os.replace the verified, fsynced candidates over the live paths (scores, land_meta,
   cards) and write PROVENANCE.json (sources, shas, MTGish MIT licence text).

Any failure in 4-5 reverts the live files to the backup immediately (Postgres was not
touched yet) and closes the transaction; if even that fails the transaction stays open
for the next run / ``card_update recover`` / the API's ExecStartPre. The transaction is
closed after rebuild + health pass (pipeline).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from card_update import txn
from card_update.context import RunContext
from card_update.fsutil import atomic_write_json, sha256_file, utc_iso
from card_update.ops import capture_baseline
from card_update.releases import CARDS, LAND_META, SCORES, ReleaseError
from card_update.stages.base import Stage, StageError, StageResult

PROVENANCE = txn.PROVENANCE


def _candidate_provenance(ctx: RunContext) -> dict[str, Any]:
    up, dl = ctx.artifacts.get("upstream", {}), ctx.artifacts.get("downloads", {})
    ver = ctx.artifacts.get("verified", {})
    lic = dl.get("mtgish_license", {})
    text = Path(lic["path"]).read_text(encoding="utf-8") if lic.get("path") and Path(lic["path"]).exists() else None
    return {
        "release_id": ctx.run_id,
        "promoted_utc": utc_iso(ctx.services.clock.now()),
        "scryfall_updated_at": up.get("scryfall", {}).get("updated_at"),
        "mtgish_sha": up.get("mtgish", {}).get("sha"),
        "cards_sha256": ver.get("cards_sha256"),
        "scoring_fingerprint": ver.get("scoring_fingerprint"),
        "unmapped_operators_sha256": ver.get("unmapped_operators_sha256"),
        "unmapped_operators": ver.get("unmapped_operators"),
        "scryfall": {"updated_at": up.get("scryfall", {}).get("updated_at"),
                     "url": dl.get("scryfall", {}).get("url"), "sha256": dl.get("scryfall", {}).get("sha256"),
                     "terms": "https://scryfall.com/docs/api (bulk data)"},
        "mtgish": {"sha": up.get("mtgish", {}).get("sha"), "url": dl.get("mtgish", {}).get("url"),
                   "sha256": dl.get("mtgish", {}).get("sha256"), "license": lic.get("name"),
                   "license_url": lic.get("url"), "license_text": text},
        "gates": ver,
    }


class PromoteStage(Stage):
    name = "promote"

    def describe(self, ctx: RunContext) -> str:
        p = ctx.config.paths
        return (f"snapshot live {p.live_cards}, {p.live_land_meta}, {p.live_scores} into {p.releases_dir}/<id>, "
                "open a durable transaction, then os.replace the verified candidates over them")

    def _check_candidate(self, ctx: RunContext) -> dict[str, Path]:
        ver = ctx.require("verified")
        cand = ctx.require("candidate")
        files = {CARDS: (cand.get("cards"), ver.get("cards_sha256")),
                 SCORES: (cand.get("scores"), ver.get("scores_sha256"))}
        if ver.get("land_meta_sha256"):
            files[LAND_META] = (cand.get("land_meta"), ver["land_meta_sha256"])
        out = {}
        for name, (path, sha) in files.items():
            if not path or not Path(path).exists() or sha256_file(Path(path)) != sha:
                raise StageError(f"candidate {name} is missing or differs from what verify passed — "
                                 "refusing to promote unverified data")
            out[name] = Path(path)
        return out

    def run(self, ctx: RunContext) -> StageResult:
        cfg, st = ctx.config, ctx.state
        if cfg.approve.enabled and ctx.manifest.stage_status("approve") != "ok":
            raise StageError("manual approval is enabled but this run has not been approved")
        if st.transaction:
            raise StageError(f"an earlier live change is unresolved ({st.transaction}); "
                             "run `python -m card_update recover` first")
        candidates = self._check_candidate(ctx)
        live_cards = cfg.paths.live_cards
        if not live_cards.exists():
            raise StageError(f"live {live_cards} missing — run `python -m card_update init` once")
        live_sha = sha256_file(live_cards)
        if st.cards_sha256 and live_sha != st.cards_sha256:
            raise StageError(f"live cards.json (sha {live_sha[:12]}) is not the recorded release "
                             f"{st.current_release_id} (sha {st.cards_sha256[:12]}): the live state is unknown; "
                             "restore a release with `card_update rollback --to <id>` first")
        backup_id = st.current_release_id or f"baseline-{live_sha[:12]}"
        ctx.artifacts["pre_promote"] = capture_baseline(cfg, ctx.services.api, ctx.log)
        try:
            ctx.releases.snapshot_live(backup_id, txn.live_provenance(cfg, st))
        except (ReleaseError, OSError) as exc:
            raise StageError(f"could not snapshot the live release (nothing changed): {exc}") from None
        txn.begin(cfg, st, kind="promote", run_id=ctx.run_id, restore_to=backup_id, needs_rebuild=False,
                  now_utc=utc_iso(ctx.services.clock.now()), phase="installing")
        ctx.extras["live_touched"] = True
        try:
            ctx.releases.install(candidates)
            provenance = _candidate_provenance(ctx)
            atomic_write_json(live_cards.parent / PROVENANCE, provenance)
            ver = ctx.artifacts["verified"]
            st.current_release_id = ctx.run_id
            st.cards_sha256 = ver["cards_sha256"]
            if ver.get("land_meta_sha256"):
                st.land_meta_sha256 = ver["land_meta_sha256"]
            st.scoring_fingerprint = ver.get("scoring_fingerprint")
            st.unmapped_operators_sha256 = ver.get("unmapped_operators_sha256")
            st.last_unmapped_operators = ver.get("unmapped_operators")
            st.last_promoted_utc = provenance["promoted_utc"]
            txn.update(cfg, st, phase="installed")
        except Exception as exc:  # noqa: BLE001 - any failure here must revert the live files
            ctx.log.error("promotion failed mid-way (%s: %s); reverting live files to %s",
                          type(exc).__name__, exc, backup_id)
            try:
                txn.Recovery(cfg, ctx.releases, ctx.services, ctx.log).resolve(
                    st, reason=f"promotion failed: {exc}", allow_rebuild=False)
                ctx.extras["live_outcome"] = f"promotion reverted: live files restored to {backup_id}"
            except (txn.RecoveryError, OSError) as rexc:
                ctx.extras["live_outcome"] = (f"LIVE FILES MAY BE MIXED: revert to {backup_id} failed ({rexc}); "
                                              "transaction left open for `card_update recover` / the next run")
            raise StageError(f"promotion failed: {type(exc).__name__}: {exc}") from None
        ctx.artifacts["promoted"] = {"release_id": ctx.run_id, "backup_release_id": backup_id,
                                     "cards_count": ctx.artifacts["verified"]["cards_count"]}
        return StageResult(summary=f"release {ctx.run_id} installed (backup: {backup_id}); "
                                   "committed after rebuild + health",
                           outputs={"backup_release_id": backup_id, "installed": sorted(candidates)})
