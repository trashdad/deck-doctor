"""Stage 6 — quality gates on the candidate vs the live release. Any violation aborts
before promote (live data untouched). Every gate logs its numbers; warnings are loud
but never block.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from card_update.context import RunContext
from card_update.diff import content_diff, render
from card_update.fingerprint import scoring_fingerprint
from card_update.fsutil import atomic_write_json, sha256_file, utc_iso
from card_update.gates import GateInputs, evaluate_all
from card_update.procs import CommandTimeout
from card_update.snapshot import load_cards, load_json_file, read_store
from card_update.stages.base import Stage, StageError, StageResult

UNMAPPED_DIR = "unmapped"    # <card_data_dir>/unmapped/<sha256>.json — content-addressed baselines


def _fmt(metrics: dict[str, Any]) -> str:
    return ", ".join(f"{k}={json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v}"
                     for k, v in metrics.items())


def unmapped_sha(ops: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(ops)).encode("utf-8")).hexdigest()


class VerifyStage(Stage):
    name = "verify"

    def describe(self, ctx: RunContext) -> str:
        return ("judge the candidate (cards.json, land_meta.json, scores.sqlite) against the live release "
                "with every gate in gates.py; any violation stops the run before promote")

    def _unmapped(self, ctx: RunContext) -> list[tuple[str, int]] | None:
        try:
            return ctx.services.bridge.unmapped_operators(Path(ctx.require("downloads")["mtgish"]["path"]))
        except (OSError, RuntimeError, ValueError, CommandTimeout) as exc:
            ctx.log.error("unmapped-operator report failed: %s", exc)
            return None

    def _unmapped_baseline(self, ctx: RunContext) -> frozenset[str] | None:
        sha = ctx.state.unmapped_operators_sha256
        if not sha:
            return None
        data, err = load_json_file(ctx.config.paths.card_data_dir / UNMAPPED_DIR / f"{sha}.json")
        if err is not None or not isinstance(data, list):
            ctx.log.warning("recorded unmapped-operator baseline %s unreadable (%s); treating as first run", sha, err)
            return None
        return frozenset(data)

    def _ier_policy(self, ctx: RunContext) -> tuple[bool, str, str]:
        current = scoring_fingerprint(ctx.config.paths.app_dir)
        recorded = ctx.state.scoring_fingerprint
        if recorded is None:
            return True, "no recorded scoring fingerprint (first run): enforcing", current
        if recorded == current:
            return True, "scoring code unchanged since the live store was built: enforcing", current
        return False, (f"scoring code differs from the code that built the live store "
                       f"({recorded[:12]} -> {current[:12]})"), current

    def run(self, ctx: RunContext) -> StageResult:
        cfg = ctx.config
        cand = ctx.require("candidate")
        if "scores" not in cand:
            raise StageError("no candidate scores.sqlite in this run (stage 'build' has not run)")
        p = cfg.paths
        if not p.live_scores.exists():
            raise StageError(f"live store {p.live_scores} missing — nothing to compare the candidate with")
        try:
            current_cards = load_cards(p.live_cards)
        except ValueError as exc:
            raise StageError(str(exc)) from None
        cand_cards, parse_err = load_json_file(Path(cand["cards"]))
        land_meta = None
        if "land_meta" in cand:
            land_meta, err = load_json_file(Path(cand["land_meta"]))
            if err is not None:
                raise StageError(f"candidate land_meta.json unreadable: {err}")
        enforce, note, fingerprint = self._ier_policy(ctx)
        ctx.log.info("IER gate: %s", note)
        unmapped = self._unmapped(ctx)
        ctx.log.info("reading live store %s and candidate store (integrity_check) ...", p.live_scores)
        inputs = GateInputs(current_cards=current_cards, candidate_cards=cand_cards,
                            current_store=read_store(p.live_scores, check_integrity=False),
                            candidate_store=read_store(Path(cand["scores"]), check_integrity=True),
                            unmapped=unmapped, land_meta=land_meta, candidate_parse_error=parse_err,
                            unmapped_baseline=self._unmapped_baseline(ctx), ier_enforced=enforce, ier_note=note)
        results = evaluate_all(inputs, cfg.gates)

        waived = set(ctx.options.waive)
        blocking, waived_hits = [], []
        for r in results:
            ctx.log.info("gate %-20s %s  %s", r.gate, "FAIL" if r.violations else "pass", _fmt(r.metrics))
            for w in r.warnings:
                ctx.log.warning("gate %s WARNING: %s", r.gate, w)
            for v in r.violations:
                if r.gate in waived:
                    waived_hits.append(v)
                    ctx.log.warning("gate %s WAIVED (--waive): %s", r.gate, v.message)
                else:
                    blocking.append(v)
                    ctx.log.error("gate %s VIOLATION: %s", r.gate, v.message)

        outputs: dict[str, Any] = {"gates": {r.gate: {"pass": not r.violations, **r.metrics} for r in results},
                                   "violations": [f"{v.gate}: {v.message}" for v in blocking],
                                   "waived": [f"{v.gate}: {v.message}" for v in waived_hits],
                                   "warnings": [w for r in results for w in r.warnings]}
        if isinstance(cand_cards, list) and not parse_err and not results[0].violations:
            diff = content_diff(current_cards, cand_cards)
            for line in render(diff):
                ctx.log.info("candidate vs live: %s", line)
            ctx.artifacts["content_diff"] = {"summary": render(diff), **diff.as_dict()}
            outputs["content_diff"] = diff.as_dict()
        if blocking:
            raise StageError(f"{len(blocking)} gate violation(s); candidate NOT promoted, live data "
                             "unchanged: " + " | ".join(f"{v.gate}: {v.message}" for v in blocking))
        ops = sorted(op for op, _ in unmapped or [])
        ops_sha = unmapped_sha(ops)
        atomic_write_json(cfg.paths.card_data_dir / UNMAPPED_DIR / f"{ops_sha}.json", ops, indent=None)
        ctx.artifacts["verified"] = {
            "utc": utc_iso(ctx.services.clock.now()),
            "cards_sha256": sha256_file(Path(cand["cards"])),
            "scores_sha256": sha256_file(Path(cand["scores"])),
            "land_meta_sha256": sha256_file(Path(cand["land_meta"])) if "land_meta" in cand else None,
            "cards_count": len(cand_cards),
            "unmapped_operators": len(ops),
            "unmapped_operators_sha256": ops_sha,
            "scoring_fingerprint": fingerprint,
            "waived": sorted(waived & {v.gate for v in waived_hits}),
        }
        return StageResult(summary=f"{len(results)} gates passed"
                           + (f" ({len(waived_hits)} violation(s) waived)" if waived_hits else ""),
                           outputs=outputs)
