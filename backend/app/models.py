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
    # Fine-grained semantic tags (e:gain_life, k:lifelink, …) — the SAME vocabulary
    # the template themes are defined in, so the Engine Board can match a card to a
    # theme/engine. Distinct from mechanic_tags (coarse zone classes).
    semantic_tags: list[str] = []
    # Commander popularity = number of corpus decks led by this card (commanders only).
    deck_count: int | None = None


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
    # Optional composition quotas (doctor keys: land/ramp/card_draw/removal/board_wipe)
    # set by the active template; /deck/complete fills toward these when present.
    template: dict[str, int] | None = None


# ---- Template system + dual-theme composite ----
class TemplateInfo(BaseModel):
    id: str
    name: str
    source: str
    counts: dict[str, int]
    notes: str = ""


class ThemeInfo(BaseModel):
    id: str
    label: str
    tags: list[str]


class TemplatesResponse(BaseModel):
    templates: list[TemplateInfo]
    themes: list[ThemeInfo]


class ThemeSuggestRequest(BaseModel):
    commander_id: str
    themes: list[str] = []
    free_text: str = ""


class ThemeSuggestion(BaseModel):
    card: Card
    score: float
    themes_matched: int


class ThemeSuggestResponse(BaseModel):
    cards: list[ThemeSuggestion]
    total: int
    has_more: bool


# ---- SP6: deck persistence ----
class DeckSummary(BaseModel):
    id: str
    name: str
    commander_id: str | None = None
    card_count: int
    updated_at: str


class DeckSave(BaseModel):
    name: str
    commander_id: str | None = None
    cards: list[DeckEntry] = []


class DeckCardOut(BaseModel):
    card: Card
    zone: str = "Utility"
    quantity: int = 1


class DeckDetail(BaseModel):
    id: str
    name: str
    commander_id: str | None = None
    created_at: str
    updated_at: str
    cards: list[DeckCardOut]


class ImportRequest(BaseModel):
    text: str
    name: str = "Imported deck"


class ImportResult(BaseModel):
    deck: DeckDetail
    unresolved: list[str] = []


# ---- parse-import (working-deck importer) -----------------------------------

class ParseImportRequest(BaseModel):
    text: str


class ParseImportUnresolved(BaseModel):
    line: str
    name: str
    quantity: int
    suggestions: list[Card] = []


class ParseImportResolved(BaseModel):
    card: Card
    zone: str
    quantity: int


class ParseImportResult(BaseModel):
    resolved: list[ParseImportResolved] = []
    unresolved: list[ParseImportUnresolved] = []
    commander_id: str | None = None


# ---- SP7: Commander Spellbook ----
class SpellbookCombo(BaseModel):
    combo_id: str
    identity: str = ""
    popularity: int | None = None
    description: str = ""
    produces: list[str] = []
    mana_needed: str = ""
    members: list[Card]


class NearCombo(BaseModel):
    combo: SpellbookCombo
    missing: Card


class DeckCombos(BaseModel):
    complete: list[SpellbookCombo]
    near: list[NearCombo]


# ---- SP8: deck doctor ----
class CompletionAdd(BaseModel):
    card: Card
    zone: str
    quantity: int = 1
    reason: str = ""


class CompleteResponse(BaseModel):
    added: list[CompletionAdd]
    final_size: int


class Cut(BaseModel):
    card: Card
    contribution: float
    reasons: list[Reason] = []


class CutsResponse(BaseModel):
    cuts: list[Cut]


# ---- SP9: synergy graph ----
class GraphNode(BaseModel):
    id: str
    name: str
    ier: float | None = None
    category: str
    image: str | None = None


class GraphEdge(BaseModel):
    a: str
    b: str
    kind: str  # "combo" | "synergy" | "cooccurrence"
    weight: float


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


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
