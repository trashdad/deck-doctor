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
| GET | `/health` | — | `{status, scores_loaded}` |
| GET | `/cards` | `q, colors, type, max_cmc, limit` | `Card[]` |
| GET | `/cards/{id}` | — | `Card` |
| GET | `/score/card/{id}` | — | `{id, ier, neighbours[]}` |
| GET | `/score/pair` | `a, b` | `PairScore` |
| POST | `/deck/analyze` | `DeckRequest` | `DeckAnalysis` |
| POST | `/deck/recommend` | `DeckRequest`, `limit` | `SynergyEdge[]` |

## Score store (SQLite, produced by `scoring/build_store.py`)
- `cards(id, name, cmc, type_line, colors, color_identity, image_normal, ier, mechanic_tags, parasitic)`
- `synergies(card_a, card_b, css, der, lift)` — top-K neighbours per card + all Lift pairs;
  indexed on `(card_a, der DESC)` and `(card_b, der DESC)` for `O(1)` reads.
