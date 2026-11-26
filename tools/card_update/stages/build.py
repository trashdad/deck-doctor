"""Stage 5 — build a CANDIDATE scores.sqlite in the run dir:
build_store -> build_semantics -> build_fingerprints. Live files are never touched.
"""

from __future__ import annotations

import os
from pathlib import Path

from card_update.context import RunContext
from card_update.fsutil import sha256_file
from card_update.procs import CommandTimeout
from card_update.snapshot import finalize_sqlite
from card_update.stages.base import Stage, StageError, StageResult


def _remove_db(path: Path) -> None:
    for p in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm"), Path(str(path) + "-journal")):
        if p.exists():
            p.unlink()


class BuildStage(Stage):
    name = "build"

    def describe(self, ctx: RunContext) -> str:
        return ("scoring/build_store.py -> build_semantics.py -> build_fingerprints.py into the run dir "
                "scores.sqlite (candidate only)")

    def run(self, ctx: RunContext) -> StageResult:
        cfg = ctx.config
        cand = ctx.require("candidate")
        mtgish = ctx.require("downloads")["mtgish"]["path"]
        py, scoring = cfg.paths.python, cfg.paths.app_dir / "scoring"
        building = ctx.workdir / "scores.building.sqlite"
        final = ctx.workdir / "scores.sqlite"
        _remove_db(building)
        cards = cand["cards"]
        steps = [
            ("build_store", [py, str(scoring / "build_store.py"), "--cards", cards, "--out", str(building),
                             "--top-k", str(cfg.build.top_k)]),
            ("build_semantics", [py, str(scoring / "build_semantics.py"), "--mtgish", mtgish,
                                 "--cards", cards, "--db", str(building)]),
            ("build_fingerprints", [py, str(scoring / "build_fingerprints.py"), "--mtgish", mtgish,
                                    "--cards", cards, "--db", str(building),
                                    "--outliers", str(cfg.paths.outliers_dir)]),
        ]
        timings = {}
        for label, argv in steps:
            try:
                res = ctx.services.runner.run(argv, cwd=cfg.paths.app_dir, label=label,
                                              timeout_s=ctx.child_timeout(cfg.build.step_timeout_minutes * 60))
            except CommandTimeout as exc:
                raise StageError(str(exc)) from None
            if res.returncode != 0:
                raise StageError(f"{label} exited {res.returncode}; candidate store abandoned; "
                                 f"last output:\n    {res.tail_text()}")
            timings[label] = round(res.duration_s, 1)
        if not building.exists():
            raise StageError(f"build produced no {building}")
        finalize_sqlite(building)
        _remove_db(final)
        os.replace(building, final)
        cand.update({"scores": str(final), "scores_sha256": sha256_file(final)})
        return StageResult(summary=f"candidate store {final.stat().st_size:,} B",
                           outputs={"durations_s": timings, "size": final.stat().st_size})
