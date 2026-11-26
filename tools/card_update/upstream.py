"""Upstream version probes: Scryfall bulk-data metadata and the MTGish commit to use."""

from __future__ import annotations

import re
from typing import Any

from card_update.config import Config
from card_update.http import FetchError, Fetcher
from card_update.state import State

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class UpstreamError(Exception):
    pass


def _scryfall(cfg: Config, fetcher: Fetcher) -> dict[str, Any]:
    meta = fetcher.get_json(cfg.upstream.scryfall_bulk_url)
    if not isinstance(meta, dict) or meta.get("type") != "default_cards":
        raise UpstreamError(f"unexpected Scryfall bulk metadata from {cfg.upstream.scryfall_bulk_url}: "
                            f"type={meta.get('type') if isinstance(meta, dict) else type(meta).__name__}")
    updated = meta.get("updated_at")
    uri = meta.get("jsonl_download_uri")      # streamed JSON lines (the array form is not used)
    if not isinstance(updated, str) or not isinstance(uri, str) or not uri.startswith("https://"):
        raise UpstreamError("Scryfall bulk metadata lacks updated_at or an https jsonl_download_uri "
                            f"(keys: {sorted(meta)})")
    size = meta.get("compressed_size")
    return {"updated_at": updated, "download_uri": uri,
            "size": size if isinstance(size, int) and size > 0 else None,
            "format": scryfall_format(uri)}


def scryfall_format(uri: str) -> str:
    path = uri.split("?", 1)[0].lower()
    for suffix in ("jsonl.gz", "jsonl"):     # streamed only; a JSON array would be loaded whole
        if path.endswith("." + suffix):
            return suffix
    raise UpstreamError(f"cannot tell the format of Scryfall bulk file {uri}")


def _mtgish(cfg: Config, fetcher: Fetcher) -> dict[str, Any]:
    pinned = cfg.upstream.mtgish_pin_sha
    if pinned:
        sha = pinned
    else:
        head = fetcher.get_json(cfg.upstream.mtgish_head_url, accept="application/vnd.github+json")
        sha = head.get("sha") if isinstance(head, dict) else None
        if not isinstance(sha, str) or not _SHA_RE.match(sha):
            raise UpstreamError(f"no commit sha in {cfg.upstream.mtgish_head_url} response")
    return {"sha": sha, "pinned": bool(pinned),
            "data_url": cfg.upstream.mtgish_data_url.format(sha=sha),
            "license_url": cfg.upstream.mtgish_license_url.format(sha=sha)}


def probe_upstream(cfg: Config, fetcher: Fetcher) -> dict[str, Any]:
    try:
        return {"scryfall": _scryfall(cfg, fetcher), "mtgish": _mtgish(cfg, fetcher)}
    except FetchError as exc:
        raise UpstreamError(str(exc)) from None


def upstream_changes(state: State, up: dict[str, Any]) -> list[str]:
    """Human-readable list of what differs from the live release ([] = nothing new)."""
    out = []
    if up["scryfall"]["updated_at"] != state.scryfall_updated_at:
        out.append(f"scryfall default-cards {state.scryfall_updated_at or 'never'} -> "
                   f"{up['scryfall']['updated_at']}")
    if up["mtgish"]["sha"] != state.mtgish_sha:
        out.append(f"mtgish {(state.mtgish_sha or 'never')[:12]} -> {up['mtgish']['sha'][:12]}")
    return out
