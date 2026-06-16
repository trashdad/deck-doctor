"""FastAPI app for the Simmander deckbuilder.

Every read is an O(1) lookup against the in-memory card map or the indexed
SQLite synergy store — no live model inference, per Doc A.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from typing import Literal

from . import config
from .analysis import analyze
from .diagnosis import diagnose
from .decks import get_userdecks
from .doctor import TEMPLATE as DOCTOR_TEMPLATE, complete_deck, suggest_cuts
from .manabase import fill_lands
from .graph import deck_graph
from .importer import parse_decklist, parse_decklist_rich
from .models import (Card, CompleteResponse, CutsResponse, DeckAnalysis, DeckCombos,
                     DeckDetail, DeckDiagnosis, DeckRequest, DeckSave, DeckSummary, EngineGroup,
                     GraphResponse, ImportRequest, ImportResult, PairScore,
                     ParseImportRequest, ParseImportResult,
                     RelationshipNeighbor, SpellbookCombo, SuggestionResponse,
                     TemplatesResponse, ThemeSuggestRequest, ThemeSuggestResponse)
from . import db
from .auth import current_user, require_user
from .store import get_store
from .suggest import is_commander, recommend
from .templates import TEMPLATES, THEMES, theme_suggest
from .export import ExportRow, to_archidekt_csv, to_manapool, to_moxfield_csv, to_text
from .ier import ier_breakdown


def _deck_detail(deck: dict) -> dict:
    """Resolve a stored deck's card ids to Card objects (drop unresolvable)."""
    store = get_store()
    cards = []
    for row in deck["cards"]:
        card = store.get(row["card_id"])
        if card is None:
            continue
        cards.append({"card": card, "zone": row["zone"], "quantity": row["quantity"]})
    return {
        "id": deck["id"], "name": deck["name"], "commander_id": deck["commander_id"],
        "created_at": deck["created_at"], "updated_at": deck["updated_at"],
        "cards": cards,
    }

_ROADMAP = "docs/superpowers/plans/2026-06-10-sp6-sp11-roadmap.md"


def _not_implemented(phase: str, section: str) -> HTTPException:
    return HTTPException(501, f"{phase} not implemented — see {_ROADMAP} {section}")

app = FastAPI(title="Deck Doctor API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    store = get_store()
    return {
        "status": "ok",
        "scores_loaded": store.scores_loaded,
        "cards": len(store._cards),
        "edhrec_commanders": len(store._edhrec),
        "spellbook_combos": len(store._spellbook),
        "engines": len(store._engines),
    }


@app.post("/admin/reload")
def admin_reload() -> dict:
    """Hot-reload the in-memory Store from disk (no restart).

    The offline pipeline (scrape → load_corpus → build_relationships →
    build_cooccurrence → import_spellbook) rewrites the sqlite stores; calling this
    drops the cached singleton so the next request rebuilds it. This is how newly
    scraped decks become visible to live recommendations — see tools/refresh_loop.py.
    """
    get_store.cache_clear()
    db.reset_pool()       # reconnect so a fresh load_to_postgres run is picked up
    store = get_store()
    return {
        "status": "reloaded",
        "cards": len(store._cards),
        "edhrec_commanders": len(store._edhrec),
        "spellbook_combos": len(store._spellbook),
        "engines": len(store._engines),
    }


@app.get("/auth/me")
def auth_me(request: Request) -> dict:
    """Current user from the shared session cookie, or null (anonymous). 200 always."""
    return {"user": current_user(request)}


@app.get("/cards", response_model=list[Card])
def search_cards(
    q: str = "",
    colors: str = "",
    type: str = "",
    oracle: str = "",
    max_cmc: float | None = None,
    commander_id: str | None = None,
    limit: int = Query(60, le=200),
) -> list[dict]:
    """Card search, most-popular first. `q` = name substring, `oracle` = oracle-text
    substring (Scryfall-style); both compose with `colors`. Pass `commander_id` to
    rank by that commander's EDHREC inclusion (empty query = top cards for them)."""
    return get_store().search(
        q=q, colors=colors, type_q=type, oracle=oracle, max_cmc=max_cmc,
        commander_id=commander_id, limit=limit)


@app.get("/cards/commanders", response_model=list[Card])
def commanders(
    q: str = "",
    colors: str = "",
    sort: Literal["popularity", "name", "ier"] = "popularity",
    limit: int = Query(0, le=2000),
) -> list[dict]:
    """Legendary creatures + planeswalkers, each enriched with `deck_count`.

    Defaults to most-played-first (corpus deck count). `q` = name substring,
    `colors` = WUBRG color-identity subset filter, `sort` = popularity|name|ier.
    """
    return get_store().commanders(q=q, colors=colors, sort=sort, limit=limit)


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


@app.get("/cards/{card_id}/ier")
def card_ier(card_id: str, request: Request) -> dict:
    """IER factor breakdown for a single card.

    Tier gate: admins are "Mythic" and receive the full factor breakdown.
    Free/anonymous users get only {locked: true, ier: <val>} — factors are
    never sent to non-Mythic users.
    """
    store = get_store()
    card = store.get(card_id)
    if not card:
        raise HTTPException(404, "card not found")
    ier_val = card.get("ier")
    if ier_val is None:
        raise HTTPException(404, "no IER score for this card")
    user = current_user(request)
    is_mythic = user is not None and bool(user.get("is_admin"))
    if not is_mythic:
        return {"locked": True, "ier": ier_val}
    breakdown = ier_breakdown(card)
    return {"locked": False, "ier": ier_val, "factors": breakdown["factors"]}


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


_EXPORT_FORMATS = {"text", "moxfield", "archidekt", "manapool"}


def _resolve_rows(req: DeckRequest) -> list[ExportRow]:
    """Resolve card ids in a DeckRequest to ExportRow dicts via the store."""
    store = get_store()
    rows: list[ExportRow] = []
    for entry in req.cards:
        card = store.get(entry.id)
        if card is None:
            continue
        rows.append({
            "name": card["name"],
            "zone": entry.zone,
            "quantity": entry.quantity,
            "commander": entry.id == req.commander_id,
        })
    return rows


@app.post("/deck/export", response_class=PlainTextResponse)
def deck_export(req: DeckRequest, format: str = Query("text")) -> str:
    """Export the current working deck in the requested format.

    Accepts the same ``DeckRequest`` body as /deck/analyze (commander_id +
    cards list).  Resolves card ids → names via the store.  No auth required —
    formats client-supplied card ids only.

    Supported formats: ``text`` (default), ``moxfield``, ``archidekt``,
    ``manapool``.  Unknown format → 400.
    """
    if format not in _EXPORT_FORMATS:
        raise HTTPException(400, f"Unknown format {format!r}. "
                            f"Accepted: {', '.join(sorted(_EXPORT_FORMATS))}")
    rows = _resolve_rows(req)
    if format == "text":
        return to_text(rows)
    if format == "moxfield":
        return to_moxfield_csv(rows)
    if format == "archidekt":
        return to_archidekt_csv(rows)
    # manapool
    return to_manapool(rows)


@app.post("/deck/parse-import", response_model=ParseImportResult)
def deck_parse_import(req: ParseImportRequest) -> dict:
    """Parse a decklist text and return resolved cards + fuzzy suggestions for misses.

    No auth required — analogous to /deck/complete (working-deck operations).
    Empty text returns an empty result (not an error).
    """
    store = get_store()
    raw = parse_decklist_rich(store, req.text)

    # Expand resolved card_id rows -> {card, zone, quantity}
    resolved = []
    for row in raw["resolved"]:
        card = store.get(row["card_id"])
        if card is None:
            continue
        resolved.append({"card": card, "zone": row["zone"], "quantity": row["quantity"]})

    # Expand unresolved rows -> {line, name, quantity, suggestions: [Card, ...]}
    unresolved = []
    for entry in raw["unresolved"]:
        suggestions = [store.get(sid) for sid in entry["suggestion_ids"]]
        suggestions = [c for c in suggestions if c is not None]
        unresolved.append({
            "line": entry["line"],
            "name": entry["name"],
            "quantity": entry["quantity"],
            "suggestions": suggestions,
        })

    return {
        "resolved": resolved,
        "unresolved": unresolved,
        "commander_id": raw["commander_id"],
    }


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


@app.post("/deck/diagnose", response_model=DeckDiagnosis)
def deck_diagnose(req: DeckRequest) -> dict:
    """Deck Doctor Diagnosis — 0–100 score + verdict + 5 vitals. Same body as
    /deck/analyze. Empty deck → score 0, verdict "—", all vitals 0."""
    store = get_store()
    return diagnose(store, [e.model_dump() for e in req.cards], req.commander_id)


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


# ---- Template system + dual-theme composite --------------------------------

@app.get("/templates", response_model=TemplatesResponse)
def templates() -> dict:
    """Composition presets (Doctor quotas) + the theme catalog (Card-free, static)."""
    return {"templates": TEMPLATES, "themes": THEMES}


@app.post("/deck/theme-suggest", response_model=ThemeSuggestResponse)
def theme_suggest_endpoint(
    req: ThemeSuggestRequest,
    limit: int = Query(10, le=60),
    offset: int = Query(0, ge=0),
) -> dict:
    """Ranked cards for the selected themes (+ free text), in the commander's colors."""
    store = get_store()
    try:
        return theme_suggest(store, req.commander_id, req.themes, req.free_text,
                             limit=limit, offset=offset)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---- SP6: deck persistence (scaffold — roadmap §6.2) -----------------------
# NOTE: /decks/import is declared before /decks/{deck_id} so "import" never
# binds as a deck_id (FastAPI matches in declaration order).

@app.get("/decks", response_model=list[DeckSummary])
def decks_list(user: dict = Depends(require_user)) -> list[dict]:
    return get_userdecks().list_decks(user["id"])


@app.post("/decks", response_model=DeckDetail, status_code=201)
def decks_create(req: DeckSave, user: dict = Depends(require_user)) -> dict:
    cards = [e.model_dump() for e in req.cards]
    deck_id = get_userdecks().create(user["id"], req.name, req.commander_id, cards)
    return _deck_detail(get_userdecks().get(deck_id, user["id"]))


@app.post("/decks/import", response_model=ImportResult)
def decks_import(req: ImportRequest, user: dict = Depends(require_user)) -> dict:
    store = get_store()
    cards, unresolved, commander_id = parse_decklist(store, req.text)
    deck_id = get_userdecks().create(user["id"], req.name, commander_id, cards)
    return {"deck": _deck_detail(get_userdecks().get(deck_id, user["id"])),
            "unresolved": unresolved}


@app.get("/decks/{deck_id}", response_model=DeckDetail)
def decks_get(deck_id: str, user: dict = Depends(require_user)) -> dict:
    deck = get_userdecks().get(deck_id, user["id"])
    if deck is None:
        raise HTTPException(404, "deck not found")
    return _deck_detail(deck)


@app.put("/decks/{deck_id}", response_model=DeckDetail)
def decks_update(deck_id: str, req: DeckSave, user: dict = Depends(require_user)) -> dict:
    cards = [e.model_dump() for e in req.cards]
    if not get_userdecks().update(deck_id, user["id"], req.name, req.commander_id, cards):
        raise HTTPException(404, "deck not found")
    return _deck_detail(get_userdecks().get(deck_id, user["id"]))


@app.delete("/decks/{deck_id}", status_code=204)
def decks_delete(deck_id: str, user: dict = Depends(require_user)) -> None:
    if not get_userdecks().delete(deck_id, user["id"]):
        raise HTTPException(404, "deck not found")


@app.get("/decks/{deck_id}/export", response_class=PlainTextResponse)
def decks_export(deck_id: str, user: dict = Depends(require_user)) -> str:
    """Export a saved deck as text.  Delegates to export.to_text (DRY)."""
    deck = get_userdecks().get(deck_id, user["id"])
    if deck is None:
        raise HTTPException(404, "deck not found")
    store = get_store()
    commander_id = deck.get("commander_id")
    rows: list[ExportRow] = []
    for row in deck["cards"]:
        card = store.get(row["card_id"])
        if card is None:
            continue
        rows.append({
            "name": card["name"],
            "zone": row["zone"],
            "quantity": row["quantity"],
            "commander": row["card_id"] == commander_id,
        })
    return to_text(rows)


# ---- SP7: Commander Spellbook (scaffold — roadmap §7.5) --------------------

def _spellbook_combo(store, combo: dict) -> dict | None:
    """Resolve a stored combo's member ids to Card objects; None if any unresolvable."""
    members = [store.get(m) for m in combo["members"]]
    if any(m is None for m in members):
        return None
    return {
        "combo_id": combo["combo_id"], "identity": combo["identity"],
        "popularity": combo["popularity"], "description": combo["description"],
        "produces": combo["produces"], "mana_needed": combo["mana_needed"],
        "members": members,
    }


@app.post("/deck/combos", response_model=DeckCombos)
def deck_combos(req: DeckRequest) -> dict:
    """Complete + one-card-away spellbook combos for the deck (commander counts as in-deck)."""
    store = get_store()
    ids = [e.id for e in req.cards]
    if req.commander_id:
        ids.append(req.commander_id)
    raw = store.deck_spellbook(ids)
    complete = [c for c in (_spellbook_combo(store, x) for x in raw["complete"]) if c]
    near = []
    for entry in raw["near"]:
        combo = _spellbook_combo(store, entry["combo"])
        missing = store.get(entry["missing"])
        if combo and missing:
            near.append({"combo": combo, "missing": missing})
    return {"complete": complete, "near": near}


@app.get("/cards/{card_id}/spellbook-combos", response_model=list[SpellbookCombo])
def card_spellbook_combos(card_id: str, limit: int = Query(20, le=60)) -> list[dict]:
    """Spellbook combos containing this card, popularity DESC. 404 unknown card."""
    store = get_store()
    if not store.get(card_id):
        raise HTTPException(404, "card not found")
    out = []
    for combo in store.spellbook_with(card_id)[:limit]:
        resolved = _spellbook_combo(store, combo)
        if resolved:
            out.append(resolved)
    return out


# ---- SP8: deck doctor (scaffold — roadmap §8.4) ----------------------------

@app.post("/deck/complete", response_model=CompleteResponse)
def deck_complete(req: DeckRequest, explain: bool = False) -> dict:
    """Complete the deck to 100 (doctor.complete_deck); 400 on missing/illegal commander."""
    store = get_store()
    if not req.commander_id or not is_commander(store.get(req.commander_id)):
        raise HTTPException(400, "commander_id must be a legendary creature or planeswalker")
    deck_ids = [e.id for e in req.cards if e.id != req.commander_id]
    # The active template (if any) sets the quotas; merge over the default so a
    # partial template still has every category complete_deck expects.
    template = {**DOCTOR_TEMPLATE, **(req.template or {})}
    result = complete_deck(store, req.commander_id, deck_ids, template=template)
    added = []
    for a in result["added"]:
        card = store.get(a["card_id"])
        if card is None:
            continue
        added.append({"card": card, "zone": a["zone"], "quantity": a["quantity"],
                      "reason": a["reason"]})
    return {"added": added, "final_size": result["final_size"]}


@app.post("/deck/lands", response_model=CompleteResponse)
def deck_lands(req: DeckRequest, max_price: float = Query(0.0, ge=0)) -> dict:
    """Fill the deck's manabase to the template's land quota.

    Only adds lands (nonbasic fixers + basics); never removes existing lands.
    Returns the same CompleteResponse shape as /deck/complete.

    max_price=0 or omitted → no price cap.
    max_price=10 → skip lands with USD price > $10 (null-priced lands always pass).
    """
    store = get_store()
    if not req.commander_id or not is_commander(store.get(req.commander_id)):
        raise HTTPException(400, "commander_id must be a legendary creature or planeswalker")
    deck_ids = [e.id for e in req.cards if e.id != req.commander_id]
    template = {**DOCTOR_TEMPLATE, **(req.template or {})}
    result = fill_lands(store, req.commander_id, deck_ids, template=template,
                        max_price=max_price)
    added = []
    for a in result:
        card = store.get(a["card_id"])
        if card is None:
            continue
        added.append({"card": card, "zone": a["zone"], "quantity": a["quantity"],
                      "reason": a["reason"]})
    final_size = 1 + len(deck_ids) + sum(a["quantity"] for a in result)
    return {"added": added, "final_size": final_size}


@app.post("/deck/cuts", response_model=CutsResponse)
def deck_cuts(req: DeckRequest, limit: int = Query(10, le=30)) -> dict:
    """Lowest-contribution cards (doctor.suggest_cuts); 400 on missing/illegal commander."""
    store = get_store()
    if not req.commander_id or not is_commander(store.get(req.commander_id)):
        raise HTTPException(400, "commander_id must be a legendary creature or planeswalker")
    deck_ids = [e.id for e in req.cards]
    cuts = []
    for c in suggest_cuts(store, req.commander_id, deck_ids, limit=limit):
        card = store.get(c["card_id"])
        if card is None:
            continue
        cuts.append({"card": card, "contribution": c["contribution"], "reasons": c["reasons"]})
    return {"cuts": cuts}


# ---- SP9: synergy graph (scaffold — roadmap §9.1) --------------------------

@app.post("/deck/graph", response_model=GraphResponse)
def deck_graph_endpoint(req: DeckRequest) -> dict:
    """Nodes + typed weighted edges among deck cards (graph.deck_graph)."""
    store = get_store()
    deck_ids = [e.id for e in req.cards]
    return deck_graph(store, req.commander_id, deck_ids)


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
