"""Ingest Commander-Spellbook combo catalogs into asserted combos.

Catalog pieces are card names; we map them to ids with the caller-supplied
name_to_id (built via fingerprints/build_semantics norm_name). Combos whose
pieces aren't all present in the corpus are skipped (can't be asserted).
"""

from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path


def _norm(name: str) -> str:
    nfkd = unicodedata.normalize("NFKD", name or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def load_catalog_combos(catalog_paths: list[str], name_to_id: dict) -> list[dict]:
    """Return asserted combos: [{combo_id, member_ids, result, steps, url}]."""
    norm_map = {_norm(k): v for k, v in name_to_id.items()}
    out: list[dict] = []
    seen: set = set()
    for path in catalog_paths:
        p = Path(path)
        if not p.is_file():
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        combos = data.get("combos", []) if isinstance(data, dict) else []
        for c in combos:
            pieces = c.get("pieces") or []
            ids = [norm_map.get(_norm(name)) for name in pieces]
            if not pieces or any(i is None for i in ids):
                continue
            combo_id = c.get("id") or "+".join(sorted(ids))
            if combo_id in seen:
                continue
            seen.add(combo_id)
            out.append({
                "combo_id": combo_id,
                "member_ids": ids,
                "result": c.get("result", ""),
                "steps": c.get("steps", ""),
                "url": c.get("source_url", ""),
            })
    return out
