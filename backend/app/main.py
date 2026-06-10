"""FastAPI app for the Simmander deckbuilder.

Every read is an O(1) lookup against the in-memory card map or the indexed
SQLite synergy store — no live model inference, per Doc A.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from typing import Literal

from . import config
from .analysis import analyze
from .models import (Card, DeckAnalysis, DeckRequest, EngineGroup, PairScore,
                     RelationshipNeighbor, SuggestionResponse)
from .store import get_store
from .suggest import is_commander, recommend

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
    result["cooccurrence"] = store.cooccurrence(a, b)
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


@app.post("/deck/recommend", response_model=SuggestionResponse)
def deck_recommend(req: DeckRequest, limit: int = Query(12, le=60),
                   explain: bool = False) -> dict:
    """SP5 commander-scoped suggestions: EDHREC synergy + co-occurrence lift +
    structural synergy + engine completion, with tiered cold-start."""
    store = get_store()
    if not req.commander_id or not is_commander(store.get(req.commander_id)):
        raise HTTPException(400, "commander_id must be a legendary creature or planeswalker")
    deck_ids = [e.id for e in req.cards]
    return recommend(store, req.commander_id, deck_ids, limit=limit, explain=explain)


@app.get("/cards/{card_id}/relationships", response_model=list[RelationshipNeighbor])
def card_relationships(
    card_id: str,
    axis: Literal["similar", "synergy", "cooccurrence"] = "synergy",
    limit: int = Query(30, le=100),
) -> list[dict]:
    """SP4: typed relationship neighbors for one card on one axis."""
    store = get_store()
    if not store.get(card_id):
        raise HTTPException(404, "card not found")
    if axis == "similar":
        pairs = store.similarity_neighbors(card_id, limit)
    elif axis == "synergy":
        pairs = store.synergy_neighbors(card_id, limit)
    else:
        pairs = [(other, lift) for other, lift, _j in
                 store.cooccurrence_neighbors(card_id, limit)]
    out = []
    for other, metric in pairs:
        card = store.get(other)
        if card:
            out.append({"card": card, "metric": round(metric, 4)})
    return out


@app.get("/cards/{card_id}/combos-engines", response_model=list[EngineGroup])
def card_combos_engines(card_id: str, limit: int = Query(30, le=100)) -> list[dict]:
    """SP4: engines/combos containing this card, members resolved to Cards."""
    store = get_store()
    if not store.get(card_id):
        raise HTTPException(404, "card not found")
    out = []
    for eng in store.engines_with(card_id)[:limit]:
        members = [store.get(m) for m in eng["members"]]
        out.append({
            "engine_id": eng["engine_id"], "kind": eng["kind"],
            "asserted": eng["asserted"], "candidate": eng["candidate"],
            "members": [m for m in members if m],
        })
    return out
