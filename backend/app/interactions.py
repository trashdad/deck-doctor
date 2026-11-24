"""Card interaction records (docs/plans/2026-11-06-card-interaction-engine.md §3).

Skeleton only: a record type, a JSONL loader (path from INTERACTIONS_JSONL env, default
unset -> no records) and `lookup`. Nothing here is wired on by default.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

KINDS = ("synergy", "combo", "anti-synergy")
KIND_WEIGHT = {"combo": 1.0, "synergy": 0.5, "anti-synergy": -0.7}
UNVERIFIED_FACTOR = 0.25


@dataclass(frozen=True)
class InteractionRecord:
    cards: tuple[str, ...]
    kind: str
    mechanism: str = ""
    evidence: tuple[dict, ...] = ()
    verified_by: str = ""           # "spellbook" | "engine" | "oracle_match" | "" (none)
    confidence: float = 0.0
    produces: tuple[dict, ...] = ()
    requires: tuple[dict, ...] = ()
    receipt: str = ""
    id: str = ""

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"bad kind {self.kind!r}")
        if len(self.cards) < 2:
            raise ValueError("an interaction needs >= 2 cards")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError("confidence must be in [0, 1]")

    @property
    def verified(self) -> bool:
        return self.verified_by not in ("", "none")

    def weight(self) -> float:
        """confidence x kind_weight, x0.25 when unverified (plan §3)."""
        w = self.confidence * KIND_WEIGHT[self.kind]
        return w if self.verified else w * UNVERIFIED_FACTOR

    @classmethod
    def from_dict(cls, d: dict) -> "InteractionRecord":
        vb = d.get("verified_by") or ""
        return cls(
            cards=tuple(d["cards"]), kind=d["kind"], mechanism=d.get("mechanism", ""),
            evidence=tuple(d.get("evidence") or ()), verified_by="" if vb == "none" else vb,
            confidence=float(d.get("confidence", 0.0)),
            produces=tuple(d.get("produces") or ()), requires=tuple(d.get("requires") or ()),
            receipt=d.get("receipt", ""), id=d.get("id", ""),
        )


def load_jsonl(path: str | Path | None) -> list[InteractionRecord]:
    """Records from a JSONL file. A malformed line (bad JSON, unknown kind, < 2 cards,
    confidence outside [0, 1], missing fields) is skipped with a warning; it never
    discards the valid lines around it."""
    if not path or not Path(path).is_file():
        return []
    out = []
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                if not isinstance(d, dict):
                    raise TypeError("record is not a JSON object")
                out.append(InteractionRecord.from_dict(d))
            except (ValueError, KeyError, TypeError) as exc:
                log.warning("interactions %s:%d skipped: %s", path, n, exc)
    return out


def lookup(records: list[InteractionRecord], deck_card_ids, candidate_id: str
           ) -> list[InteractionRecord]:
    """Records containing the candidate whose OTHER pieces are all in the deck.

    Plan §3: a k-card record contributes when >= k-1 pieces are already in the deck
    (the candidate completes it). For k = 2 that is "the one partner is in the deck"."""
    deck = set(deck_card_ids) - {candidate_id}
    return [r for r in records
            if candidate_id in r.cards
            and all(c in deck for c in r.cards if c != candidate_id)]


def default_records() -> list[InteractionRecord]:
    return load_jsonl(os.environ.get("INTERACTIONS_JSONL"))
