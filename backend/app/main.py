"""FastAPI app for the Simmander deckbuilder.

Every read is an O(1) lookup against the in-memory card map or the indexed
SQLite synergy store — no live model inference, per Doc A.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .analysis import analyze
from .models import Card, DeckAnalysis, DeckRequest, PairScore, SynergyEdge
from .store import get_store

app = FastAPI(title="Simmander Deckbuilder API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    store = get_store()
    return {"status": "ok", "scores_loaded": store.scores_path.exists()}


@app.get("/cards", response_model=list[Card])
def search_cards(
    q: str = "",
    colors: str = "",
    type: str = "",
    max_cmc: float | None = None,
    limit: int = Query(60, le=200),
) -> list[dict]:
    return get_store().search(q=q, colors=colors, type_q=type, max_cmc=max_cmc, limit=limit)


@app.get("/cards/commanders", response_model=list[Card])
def commanders() -> list[dict]:
    """All legendary creatures + legendary planeswalkers legal in Commander."""
    store = get_store()
    results = []
    for card in store._cards.values():
        tl = (card.get("type_line") or "").lower()
        if "legendary" not in tl:
            continue
        if "creature" not in tl and "planeswalker" not in tl:
            continue
        enriched = store.get(card["id"])
        if enriched:
            results.append(enriched)
    results.sort(key=lambda c: c.get("name", ""))
    return results


@app.get("/cards/oracle", response_model=list[Card])
def oracle_search(
    pattern: str,
    limit: int = Query(50, le=200),
) -> list[dict]:
    if len(pattern.strip()) < 4:
        raise HTTPException(400, "pattern must be at least 4 characters")
    return get_store().oracle_search(pattern=pattern.strip(), limit=limit)


@app.get("/cards/{card_id}/semantics")
def card_semantics(card_id: str) -> dict:
    """Return {flat_tags, ability_tags} for a card."""
    store = get_store()
    if not store.get(card_id):
        raise HTTPException(404, "card not found")
    return store.card_semantics(card_id)


@app.get("/cards/by-semantics", response_model=list[Card])
def cards_by_semantics(
    linked_tags: str = Query("", description="Tags that must co-appear on same ability"),
    flat_tags: str = Query("", description="Tags that must appear anywhere on card"),
    limit: int = Query(50, le=200),
) -> list[dict]:
    lt = [t.strip() for t in linked_tags.split(",") if t.strip()]
    ft = [t.strip() for t in flat_tags.split(",") if t.strip()]
    if not lt and not ft:
        raise HTTPException(400, "linked_tags or flat_tags required")
    return get_store().search_by_semantics_mixed(lt, ft, limit=limit)


@app.get("/cards/{card_id}/similar", response_model=list[Card])
def similar_cards(card_id: str, limit: int = Query(20, le=60)) -> list[dict]:
    """Cards most semantically similar (TF-IDF cosine on tag vectors)."""
    store = get_store()
    if not store.get(card_id):
        raise HTTPException(404, "card not found")
    return store.similar_cards(card_id, limit=limit)


@app.get("/cards/{card_id}/combos", response_model=list[Card])
def combo_cards(card_id: str, limit: int = Query(20, le=60)) -> list[dict]:
    """Cards that best complement this one (semantic complement pairs)."""
    store = get_store()
    if not store.get(card_id):
        raise HTTPException(404, "card not found")
    return store.combo_cards(card_id, limit=limit)


@app.get("/cards/{card_id}", response_model=Card)
def get_card(card_id: str) -> dict:
    card = get_store().get(card_id)
    if not card:
        raise HTTPException(404, "card not found")
    return card


@app.get("/score/card/{card_id}")
def score_card(card_id: str) -> dict:
    store = get_store()
    ier = store.ier(card_id)
    if ier is None:
        raise HTTPException(404, "no score for card (build the store?)")
    return {"id": card_id, "ier": ier, "neighbours": store.neighbours(card_id)}


@app.get("/score/pair", response_model=PairScore)
def score_pair(a: str, b: str) -> dict:
    store = get_store()
    edge = store.pair(a, b)
    ier_a, ier_b = store.ier(a), store.ier(b)
    if ier_a is None or ier_b is None:
        raise HTTPException(404, "unknown card(s)")
    css = edge["css"] if edge else 0.0
    der = edge["der"] if edge else round(ier_a + ier_b, 2)
    result = {"a": a, "b": b, "ier_a": ier_a, "ier_b": ier_b,
              "css": css, "der": der, "lift": bool(edge and edge["lift"])}
    result["relationship"] = store.relationship(a, b)
    return result


@app.post("/deck/engines")
def deck_engines(req: DeckRequest) -> dict:
    """Return engines and combos from the prebuilt engines table that are fully present in the deck."""
    store = get_store()
    ids = [e.id for e in req.cards]
    return store.deck_engines(ids)


@app.post("/deck/analyze", response_model=DeckAnalysis)
def deck_analyze(req: DeckRequest) -> dict:
    store = get_store()
    return analyze(store, [e.model_dump() for e in req.cards], req.commander_id)


@app.post("/deck/recommend", response_model=list[SynergyEdge])
def deck_recommend(req: DeckRequest, limit: int = 12) -> list[dict]:
    """Lift-based suggestions: highest-DER neighbours of the current list that
    aren't already in the deck (PowerTune-style)."""
    store = get_store()
    in_deck = {e.id for e in req.cards}
    suggestions: dict[str, dict] = {}
    for e in req.cards:
        for edge in store.neighbours(e.id, limit=20):
            other = edge["card_b"] if edge["card_a"] == e.id else edge["card_a"]
            if other in in_deck:
                continue
            if other not in suggestions or edge["der"] > suggestions[other]["der"]:
                suggestions[other] = edge
    return sorted(suggestions.values(), key=lambda x: x["der"], reverse=True)[:limit]
