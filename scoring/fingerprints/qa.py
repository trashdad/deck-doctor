"""QA gates: golden regression, coverage report, unmapped-operator report."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tag_taxonomy import ACTION_MAP, TRIGGER_MAP  # noqa: E402

from .schema import AbilityRecord  # noqa: E402


def golden_diff(records: list[AbilityRecord], golden: list[dict]) -> list[str]:
    """Return human-readable diffs; empty list == exact match."""
    diffs: list[str] = []
    got = [r.to_dict() for r in records]
    if len(got) != len(golden):
        diffs.append(f"ability count {len(got)} != golden {len(golden)}")
    for i, (g, e) in enumerate(zip(got, golden)):
        if g != e:
            diffs.append(f"ability_idx {i} differs")
    return diffs


def _collect_ops(node: Any, kind: str, seen: Counter, depth: int = 0) -> None:
    if depth > 25:
        return
    if isinstance(node, dict):
        v = node.get(kind)
        if isinstance(v, str):
            seen[v] += 1
        for x in node.values():
            _collect_ops(x, kind, seen, depth + 1)
    elif isinstance(node, list):
        for x in node:
            _collect_ops(x, kind, seen, depth + 1)


def unmapped_operators(cards: list[dict]) -> list[tuple[str, int]]:
    """Operators present in the corpus that ACTION_MAP/TRIGGER_MAP don't name.

    Occurrence-weighted, descending. This is the shrinking backlog + new-set guard.
    """
    actions: Counter = Counter()
    triggers: Counter = Counter()
    for c in cards:
        _collect_ops(c.get("Rules", []), "_Action", actions)
        _collect_ops(c.get("Rules", []), "_Trigger", triggers)
    out: Counter = Counter()
    for op, n in actions.items():
        if op not in ACTION_MAP and op not in _STRUCTURAL:
            out[op] += n
    for op, n in triggers.items():
        if op not in TRIGGER_MAP:
            out[op] += n
    return out.most_common()


# Structural ops the projector handles directly (not "unmapped" leaf verbs).
_STRUCTURAL = {
    "If", "Unless", "IfElse", "MayAction", "MayActions",
    "PlayerAction", "EachPlayerAction",
}


def coverage_report(per_card_tags: dict[str, list[str]], total_cards: int) -> dict:
    nonempty = sum(1 for t in per_card_tags.values() if t)
    return {
        "total_cards": total_cards,
        "with_records": nonempty,
        "coverage_pct": round(100.0 * nonempty / total_cards, 2) if total_cards else 0.0,
    }
