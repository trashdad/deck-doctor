"""Stage 2 — download Scryfall default-cards and the pinned MTGish data + licence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from card_update.context import RunContext
from card_update.fsutil import atomic_write_text, free_bytes, sha256_file
from card_update.http import FetchError
from card_update.stages.base import Stage, StageError, StageResult


def _reusable(prev: dict[str, Any] | None, url: str, dest: Path) -> bool:
    """A download from an earlier attempt of this run is reused if it is intact."""
    return bool(prev and prev.get("url") == url and dest.exists()
                and dest.stat().st_size == prev.get("size") and sha256_file(dest) == prev.get("sha256"))


def _check_mtgish_lines(path: Path) -> None:
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                try:
                    first = json.loads(line)
                except ValueError as exc:
                    raise StageError(f"{path} is not MTGish JSON lines: {exc}") from None
                if not isinstance(first, dict) or "Name" not in first or "Rules" not in first:
                    raise StageError(f"{path}: first record lacks Name/Rules — upstream format changed?")
                return
    raise StageError(f"{path} is empty")


class FetchStage(Stage):
    name = "fetch"

    def describe(self, ctx: RunContext) -> str:
        return ("download Scryfall default-cards (size-checked against the bulk metadata, sha256 "
                "recorded) and MTGish mtgish.lines.json + LICENSE at the checked commit into the run dir")

    def run(self, ctx: RunContext) -> StageResult:
        cfg, f = ctx.config, ctx.services.fetcher
        up = ctx.require("upstream")
        free = free_bytes(ctx.workdir)
        if free < cfg.fetch.min_free_bytes:
            raise StageError(f"only {free:,} bytes free under {ctx.workdir}; need "
                             f"{cfg.fetch.min_free_bytes:,} (fetch.min_free_bytes) — free disk space")
        prev = ctx.artifacts.get("downloads", {})
        out: dict[str, Any] = {}
        sc = up["scryfall"]
        dest = ctx.workdir / f"default-cards.{sc['format']}"
        try:
            if _reusable(prev.get("scryfall"), sc["download_uri"], dest):
                ctx.log.info("reusing intact %s from an earlier attempt", dest.name)
                out["scryfall"] = prev["scryfall"]
            else:
                r = f.download(sc["download_uri"], dest, expected_size=sc["size"],
                               min_size=cfg.fetch.scryfall_min_bytes, max_size=cfg.fetch.scryfall_max_bytes)
                out["scryfall"] = {"url": r.url, "path": str(r.path), "size": r.size, "sha256": r.sha256,
                                   "format": sc["format"], "updated_at": sc["updated_at"]}
            mt = up["mtgish"]
            mdest = ctx.workdir / f"mtgish.lines.{mt['sha']}.json"
            if _reusable(prev.get("mtgish"), mt["data_url"], mdest):
                out["mtgish"] = prev["mtgish"]
            else:
                r = f.download(mt["data_url"], mdest, min_size=cfg.fetch.mtgish_min_bytes,
                               max_size=cfg.fetch.mtgish_max_bytes)
                out["mtgish"] = {"url": r.url, "path": str(r.path), "size": r.size, "sha256": r.sha256,
                                 "sha": mt["sha"]}
            _check_mtgish_lines(Path(out["mtgish"]["path"]))
            text = f.get_text(mt["license_url"], max_bytes=200_000)
        except FetchError as exc:
            raise StageError(f"download failed: {exc}") from None
        must = cfg.upstream.mtgish_license_must_contain
        if must not in text:
            raise StageError(f"MTGish LICENSE at {mt['sha'][:12]} no longer contains {must!r} — "
                             "licence changed; not using this data until someone reviews it")
        lic = ctx.workdir / f"mtgish.LICENSE.{mt['sha']}.txt"
        atomic_write_text(lic, text)
        out["mtgish_license"] = {"url": mt["license_url"], "path": str(lic), "name": must}
        ctx.artifacts["downloads"] = out
        return StageResult(summary=f"scryfall {out['scryfall']['size']:,} B, mtgish {out['mtgish']['size']:,} B",
                           outputs={k: {kk: vv for kk, vv in v.items() if kk != "path"} for k, v in out.items()})
