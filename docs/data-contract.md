# Data Contract

The frontend TS types and backend Pydantic models describe the same shapes and must stay in lockstep.

| Concept | Frontend | Backend |
| --- | --- | --- |
| Card | `frontend/src/lib/types.ts::Card` | `backend/app/models.py::Card` |
| Synergy edge | `…::SynergyEdge` | `…::SynergyEdge` |
| Deck entry | `…::DeckEntry` | `…::DeckEntry` |
| Deck analysis | `…::DeckAnalysis` | `…::DeckAnalysis` / `DeckRequest` |

## Card (Scryfall-compatible subset)
`id, name, cmc, type_line, oracle_text, colors[], color_identity[], power, toughness, keywords[],
image_uris.normal` plus enrichment from the score store: `ier`, `mechanic_tags[]`.

## Endpoints
| Method | Path | Body / Query | Returns |
| --- | --- | --- | --- |
| GET | `/health` | — | `{status, scores_loaded, cards, edhrec_commanders, spellbook_combos, engines}` |
| POST | `/admin/reload` | — | hot-reloads the in-memory Store; returns corpus sizes |
| GET | `/cards` | `q, colors, type, max_cmc, limit` | `Card[]` |
| GET | `/cards/commanders` | — | `Card[]` (legendary creatures/planeswalkers) |
| GET | `/cards/{id}` | — | `Card` |
| GET | `/cards/{id}/relationships` | `axis=similar\|synergy\|cooccurrence, limit` | `RelationshipNeighbor[]` (SP4) |
| GET | `/cards/{id}/combos-engines` | `limit` | `EngineGroup[]` (SP4) |
| GET | `/cards/{id}/spellbook-combos` | `limit` | `SpellbookCombo[]` (SP7) |
| GET | `/score/card/{id}` | — | `{id, ier, neighbours[]}` |
| GET | `/score/pair` | `a, b` | `PairScore` (+ relationship + cooccurrence blocks) |
| POST | `/deck/analyze` | `DeckRequest` | `DeckAnalysis` |
| POST | `/deck/recommend` | `DeckRequest`, `limit`, `explain` | `SuggestionResponse` (SP5) |
| POST | `/deck/combos` | `DeckRequest` | `DeckCombos{complete, near}` (SP7) |
| POST | `/deck/complete` | `DeckRequest`, `explain` | `CompleteResponse{added, final_size}` (SP8) |
| POST | `/deck/cuts` | `DeckRequest`, `limit` | `CutsResponse{cuts}` (SP8) |
| POST | `/deck/graph` | `DeckRequest` | `GraphResponse{nodes, edges}` (SP9) |
| POST | `/deck/engines` | `DeckRequest` | `{engines, combos}` |
| GET | `/decks` · POST `/decks` · GET/PUT/DELETE `/decks/{id}` | `DeckSave` | `DeckSummary[]` / `DeckDetail` (SP6) |
| POST | `/decks/import` | `ImportRequest{text, name}` | `ImportResult{deck, unresolved}` (SP6) |
| GET | `/decks/{id}/export` | — | `text/plain` decklist (SP6) |

## Score store (SQLite, produced by `scoring/build_store.py`)
- `cards(id, name, cmc, type_line, colors, color_identity, image_normal, ier, mechanic_tags, parasitic)`
- `synergies(card_a, card_b, css, der, lift)` — top-K neighbours per card + all Lift pairs;
  indexed on `(card_a, der DESC)` and `(card_b, der DESC)` for `O(1)` reads.
