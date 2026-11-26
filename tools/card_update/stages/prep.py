"""Stage 3 — Scryfall bulk -> JSON array -> scoring/prep_cards.py --keep-ids-from <live>.

The JSONL is streamed into the JSON array prep_cards reads, keeping only prints that pass
prep_cards' own filter (``_keep``), so the output is identical while the file (and
prep_cards' memory use) shrinks. Stops with nothing-to-do when the resulting cards.json
is byte-identical to the live one and MTGish did not move.
"""

from __future__ import annotations

import gzip
import json
import os
from pathlib import Path
from typing import IO, Any, Callable, Iterator

from card_update.context import RunContext
from card_update.fsutil import sha256_file
from card_update.procs import CommandTimeout
from card_update.stages.base import Outcome, Stage, StageError, StageResult


def _open_binary(path: Path, fmt: str) -> IO[bytes]:
    if fmt not in ("jsonl", "jsonl.gz"):
        raise StageError(f"unsupported Scryfall bulk format {fmt!r}: only (gzipped) JSON lines are streamed")
    return gzip.open(path, "rb") if fmt.endswith(".gz") else open(path, "rb")


def _iter_prints(path: Path, fmt: str, max_bytes: int, max_lines: int) -> Iterator[dict]:
    """Stream JSONL prints with hard caps on decompressed bytes and line count."""
    seen = 0
    with _open_binary(path, fmt) as fh:
        for lineno, raw in enumerate(fh, 1):
            seen += len(raw)
            if seen > max_bytes:
                raise StageError(f"{path.name} decompresses to more than {max_bytes:,} bytes "
                                 "(prep.max_decompressed_bytes) — refusing")
            if lineno > max_lines:
                raise StageError(f"{path.name} has more than {max_lines:,} lines (prep.max_scryfall_prints)")
            if not raw.strip():
                continue
            try:
                obj = json.loads(raw)
            except ValueError as exc:
                raise StageError(f"{path.name} line {lineno} is not JSON ({exc}) — truncated download?") from None
            yield obj


def convert_to_array(src: Path, fmt: str, dest: Path, keep: Callable[[dict], bool],
                     max_bytes: int = 6_000_000_000, max_lines: int = 1_000_000) -> dict[str, int]:
    """Stream Scryfall bulk JSONL into a JSON array of the prints prep_cards would keep."""
    prints = kept = 0
    part = dest.with_name(dest.name + ".part")
    try:
        with open(part, "w", encoding="utf-8") as out:
            out.write("[")
            for card in _iter_prints(src, fmt, max_bytes, max_lines):
                prints += 1
                if not isinstance(card, dict) or "id" not in card:
                    raise StageError(f"{src.name}: print #{prints} has no id — unexpected format")
                if not keep(card):
                    continue
                out.write(",\n" if kept else "\n")
                out.write(json.dumps(card, ensure_ascii=False, separators=(",", ":")))
                kept += 1
            out.write("\n]\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(part, dest)
    finally:
        if part.exists():
            part.unlink()
    return {"prints": prints, "kept": kept}


class PrepStage(Stage):
    name = "prep"

    def describe(self, ctx: RunContext) -> str:
        return (f"stream the bulk file into default-cards.json (prep_cards filter), then "
                f"scoring/prep_cards.py --keep-ids-from {ctx.config.paths.live_cards} -> run dir cards.json; "
                "nothing-to-do if identical to live and MTGish unchanged")

    def run(self, ctx: RunContext) -> StageResult:
        cfg = ctx.config
        live = cfg.paths.live_cards
        if not live.exists():
            raise StageError(f"live cards file {live} is missing — run `python -m card_update init` once "
                             "(seeds it from the tracked data/cards.json)")
        dl = ctx.require("downloads")["scryfall"]
        array = ctx.workdir / "default-cards.json"
        stats = convert_to_array(Path(dl["path"]), dl["format"], array, ctx.services.bridge.keep_card(),
                                 max_bytes=cfg.prep.max_decompressed_bytes, max_lines=cfg.prep.max_scryfall_prints)
        ctx.log.info("bulk file: %s prints, %s pass prep_cards' filter", f"{stats['prints']:,}", f"{stats['kept']:,}")
        if stats["prints"] < cfg.prep.min_scryfall_prints:
            raise StageError(f"Scryfall bulk file has only {stats['prints']:,} prints (< prep.min_scryfall_prints "
                             f"{cfg.prep.min_scryfall_prints:,}) — truncated or wrong file")
        cards = ctx.workdir / "cards.json"
        part = ctx.workdir / "cards.json.part"
        argv = [cfg.paths.python, str(cfg.paths.app_dir / "scoring" / "prep_cards.py"),
                "--src", str(array), "--out", str(part), "--keep-ids-from", str(live)]
        try:
            res = ctx.services.runner.run(argv, cwd=cfg.paths.app_dir, label="prep_cards",
                                          timeout_s=ctx.child_timeout(cfg.prep.timeout_minutes * 60))
        except CommandTimeout as exc:
            raise StageError(str(exc)) from None
        if res.returncode != 0 or not part.exists():
            raise StageError(f"prep_cards.py exited {res.returncode}; last output:\n    {res.tail_text()}")
        os.replace(part, cards)
        array.unlink()                      # regenerable from the kept download; saves ~0.5 GB
        with open(cards, encoding="utf-8") as fh:
            count = len(json.load(fh))
        cand_sha, live_sha = sha256_file(cards), sha256_file(live)
        ctx.artifacts["candidate"] = {"cards": str(cards), "cards_sha256": cand_sha, "cards_count": count}
        outputs: dict[str, Any] = {**stats, "cards": count, "cards_sha256": cand_sha, "live_sha256": live_sha}
        mtgish_same = ctx.require("upstream")["mtgish"]["sha"] == ctx.state.mtgish_sha
        if cand_sha == live_sha and mtgish_same and not ctx.options.force:
            return StageResult(Outcome.NOTHING_TO_DO,
                               f"cards.json identical to live ({count:,} cards) and MTGish unchanged; "
                               "recording the new Scryfall stamp only", outputs)
        return StageResult(summary=f"{count:,} cards ({'identical to' if cand_sha == live_sha else 'differs from'} live)",
                           outputs=outputs)
