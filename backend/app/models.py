"""Pydantic models — the data contract shared (in shape) with the frontend TS types.

Keep these in lockstep with frontend/src/lib/types.ts.
"""

from __future__ import annotations

from pydantic import BaseModel


class ImageUris(BaseModel):
    normal: str | None = None


class Card(BaseModel):
    id: str
    name: str
    cmc: float = 0
    type_line: str = ""
    oracle_text: str = ""
    colors: list[str] = []
    color_identity: list[str] = []
    power: str | None = None
    toughness: str | None = None
    keywords: list[str] = []
    image_uris: ImageUris | None = None
    # Enriched from the score store when available.
    ier: float | None = None
    mechanic_tags: list[str] = []


class PairScore(BaseModel):
    a: str
    b: str
    ier_a: float
    ier_b: float
    css: float
    der: float
    lift: bool
    relationship: dict | None = None
    cooccurrence: dict | None = None


class SynergyEdge(BaseModel):
    card_a: str
    card_b: str
    css: float
    der: float
    lift: bool


class Reason(BaseModel):
    signal: str
    detail: str
    value: float


class Suggestion(BaseModel):
    card: Card
    score: float
    reasons: list[Reason] = []


class SuggestionResponse(BaseModel):
    tier: str  # "edhrec" | "cooccurrence" | "color_staple"
    suggestions: list[Suggestion]


class RelationshipNeighbor(BaseModel):
    card: Card
    metric: float


class EngineGroup(BaseModel):
    engine_id: str
    kind: str
    asserted: bool
    candidate: bool
    members: list[Card]


class DeckEntry(BaseModel):
    id: str
    zone: str = "Unsorted"
    quantity: int = 1


class DeckRequest(BaseModel):
    commander_id: str | None = None
    cards: list[DeckEntry]


class CurveBucket(BaseModel):
    cmc: int
    count: int


class DeckAnalysis(BaseModel):
    card_count: int
    mana_curve: list[CurveBucket]
    color_pips: dict[str, int]
    type_counts: dict[str, int]
    # DeckCheck-style gauges.
    efficiency: float          # 0–10 (mean IER scaled)
    impact: float              # 0–10 (top-end synergy density)
    average_playability: float  # 0–100 %
    score: int                 # 0–1000
    bracket: int               # 1–5 (Moxfield-style)
    bracket_reasons: list[str]
    top_synergies: list[SynergyEdge]
    # Deckstats-style probability that you draw >=1 of a key category by a turn.
    keepable_hand_pct: float
