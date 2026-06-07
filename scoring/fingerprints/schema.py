"""Dataclasses for the structured card fingerprint.

A card -> list[AbilityRecord]. Each ability -> Effects. Amounts are composable
(literal | x | dynamic) per the Forge Count$ / XMage DynamicValue prior art.
All dataclasses are JSON-round-trippable so they persist as a single `record`
column and reload identically (golden-regression depends on exact equality).
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional

# Allowed ability kinds (CR-flavoured; extended for replacement/prevention/restriction).
KINDS = ("triggered", "activated", "static", "spell",
         "replacement", "prevention", "restriction")


@dataclass
class Amount:
    kind: str = "literal"                 # "literal" | "x" | "dynamic"
    value: Optional[int] = None           # set when kind == "literal"
    count: Optional[dict] = None          # set when kind == "dynamic"

    def to_dict(self) -> dict:
        return {"kind": self.kind, "value": self.value, "count": self.count}

    @classmethod
    def from_dict(cls, d: dict) -> "Amount":
        return cls(kind=d.get("kind", "literal"),
                   value=d.get("value"), count=d.get("count"))


@dataclass
class Effect:
    verb: str                              # raw MTGish _Action op (lossless)
    object: Optional[str] = None           # affected object TYPE (e.g. "creature")
    prefixes: list[str] = field(default_factory=list)   # other/another/target/each
    scope: Optional[str] = None            # who/what affected (recipient/player token)
    quantifier: Optional[str] = None       # all | each | single | up_to | n
    targeted: bool = False                 # targets vs affects-without-targeting
    amount: Optional[Amount] = None
    duration: Optional[str] = None
    grants: Optional[str] = None           # keyword granted (innate-vs-granted)
    optional: bool = False
    sub_effects: list["Effect"] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "verb": self.verb, "object": self.object, "prefixes": self.prefixes,
            "scope": self.scope, "quantifier": self.quantifier,
            "targeted": self.targeted,
            "amount": self.amount.to_dict() if self.amount else None,
            "duration": self.duration, "grants": self.grants,
            "optional": self.optional,
            "sub_effects": [e.to_dict() for e in self.sub_effects],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Effect":
        return cls(
            verb=d["verb"], object=d.get("object"),
            prefixes=list(d.get("prefixes") or []),
            scope=d.get("scope"), quantifier=d.get("quantifier"),
            targeted=bool(d.get("targeted", False)),
            amount=Amount.from_dict(d["amount"]) if d.get("amount") else None,
            duration=d.get("duration"), grants=d.get("grants"),
            optional=bool(d.get("optional", False)),
            sub_effects=[cls.from_dict(x) for x in (d.get("sub_effects") or [])],
        )


@dataclass
class AbilityRecord:
    ability_idx: int
    kind: str = "static"
    trigger: Optional[dict] = None
    cost: Optional[dict] = None
    timing: Optional[str] = None
    condition: Optional[dict] = None
    optional: bool = False
    modal: Optional[dict] = None
    effects: list[Effect] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "ability_idx": self.ability_idx, "kind": self.kind,
            "trigger": self.trigger, "cost": self.cost, "timing": self.timing,
            "condition": self.condition, "optional": self.optional,
            "modal": self.modal,
            "effects": [e.to_dict() for e in self.effects],
            "raw": self.raw,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AbilityRecord":
        return cls(
            ability_idx=d["ability_idx"], kind=d.get("kind", "static"),
            trigger=d.get("trigger"), cost=d.get("cost"), timing=d.get("timing"),
            condition=d.get("condition"), optional=bool(d.get("optional", False)),
            modal=d.get("modal"),
            effects=[Effect.from_dict(x) for x in (d.get("effects") or [])],
            raw=d.get("raw") or {},
        )
