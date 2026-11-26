"""Stage 4 — land prices + produced_mana from Scryfall's collection endpoint
(backend/scripts/enrich_lands.py logic: same batching, throttle and field extraction),
written to the run dir. Unlike the script it fails loudly instead of writing partial data.
"""

from __future__ import annotations

import json
from typing import Any

from card_update.context import RunContext
from card_update.fsutil import atomic_write_text, sha256_file
from card_update.http import FetchError
from card_update.stages.base import Stage, StageError, StageResult


class EnrichStage(Stage):
    name = "enrich"

    def describe(self, ctx: RunContext) -> str:
        e = ctx.config.enrich
        return (f"POST land ids in batches of {e.batch_size} to {ctx.config.upstream.scryfall_collection_url} "
                f"({e.interval_s}s apart) -> run dir land_meta.json; fail if > {e.max_error_batches} batch(es) fail")

    def run(self, ctx: RunContext) -> StageResult:
        cfg = ctx.config
        cand = ctx.require("candidate")
        mod = ctx.services.bridge.enrich_module()
        batch_size = min(cfg.enrich.batch_size, int(getattr(mod, "BATCH_SIZE", 75)))
        interval = max(cfg.enrich.interval_s, getattr(mod, "SLEEP_MS", 150) / 1000.0)
        with open(cand["cards"], encoding="utf-8") as fh:
            cards = json.load(fh)
        land_ids = [c["id"] for c in cards if "Land" in (c.get("type_line") or "")]
        batches = [land_ids[i:i + batch_size] for i in range(0, len(land_ids), batch_size)]
        ctx.log.info("%d land cards in %d batches", len(land_ids), len(batches))
        meta: dict[str, Any] = {}
        failed: list[str] = []
        not_found = 0
        for i, batch in enumerate(batches):
            if i:
                ctx.services.clock.sleep(interval)
            try:
                body = ctx.services.fetcher.post_json(cfg.upstream.scryfall_collection_url,
                                                      {"identifiers": [{"id": cid} for cid in batch]})
            except FetchError as exc:
                failed.append(f"batch {i + 1}: {exc}")
                ctx.log.error("batch %d/%d FAILED: %s", i + 1, len(batches), exc)
                continue
            for card in body.get("data", []) if isinstance(body, dict) else []:
                if card.get("id"):
                    meta[card["id"]] = mod.extract_meta(card)
            not_found += len(body.get("not_found", []) or []) if isinstance(body, dict) else 0
        if len(failed) > cfg.enrich.max_error_batches:
            raise StageError(f"{len(failed)} of {len(batches)} Scryfall collection batches failed "
                             f"(max {cfg.enrich.max_error_batches}); not writing partial land data: {failed[:3]}")
        out = ctx.workdir / "land_meta.json"
        atomic_write_text(out, json.dumps(meta, ensure_ascii=False, indent=2))
        with_price = sum(1 for v in meta.values() if v.get("usd") is not None)
        cand.update({"land_meta": str(out), "land_meta_sha256": sha256_file(out), "land_meta_count": len(meta)})
        return StageResult(summary=f"{len(meta):,}/{len(land_ids):,} lands enriched ({with_price:,} priced)",
                           outputs={"lands": len(land_ids), "entries": len(meta), "with_price": with_price,
                                    "not_found": not_found, "failed_batches": len(failed)})
