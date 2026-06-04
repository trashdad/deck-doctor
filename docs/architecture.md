# Architecture

## Goal

A deck-building website for simmander.app with a robust, clean GUI that renders **real Magic card art** and
organizes cards into designated category **zones** (ramp, removal, card draw, win-cons, lands…). Power and
synergy are computed **offline** and read by the live site in `O(1)` — no live LLM, microsecond responses.

## Scoring vocabulary (from the research docs)

| Term | Meaning | Where |
| --- | --- | --- |
| **IER** | Isolated Efficiency Rating — a card's value in a vacuum, `1.0–20.0`, from mana value, card advantage, raw stats. | `scoring/simmander_scoring/evaluate.py::isolated_efficiency_rating` |
| **CSS** | Combinatorial Synergy Score — multiplier for how two mechanics overlap. `0` = none, `~1` = linear, `2.0+` = exponential. | `…::combinatorial_synergy_score` |
| **DER** | Dynamic Efficiency Ratio — realized value of a pair: `DER = IER_A + IER_B + (IER_A × CSS)`. | `…::dynamic_efficiency_ratio` |
| **Lift** | Association-rule flag for "parasitic" mechanic clusters (infect, energy, mutate) that uniquely bind cards. | `…::has_lift` |

**Formula note.** The doc's worked example (IER 5.6 + 13.1, additive 18.7, synergistic DER 45.3) is only
self-consistent if `CSS = 0` means *no synergy* (`DER == additive`). We treat CSS as starting at 0 and
climbing with overlap; this single source of truth lives in `evaluate.py`'s module docstring.

## Three historical approaches, and what we use

The research surveyed three ways to score synergy offline:
1. **Association-rule "Lift"** (EDHREC) — market-basket lift over co-occurrence; filters out staples.
2. **Collaborative filtering / matrix factorization** (Recommander) — latent features from decklists.
3. **Vector embeddings / latent space** (EDH.tools) — encode rules text & mechanics, cluster by behavior.

We use a **hybrid of vector/mechanic embeddings + Lift**, computed entirely offline. Mechanic tags
(`mechanics.py`) approximate the embedding's behavioral clustering cheaply and deterministically; Lift flags
the parasitic clusters. The semantic-embedding upgrade (sentence-transformers + FAISS) plugs in behind the
same interfaces for the full 32k corpus.

## Why offline + O(1)

A full 32k × 32k DER matrix is ~5×10⁸ unordered pairs — impractical to store and pointless to query live.
Instead `scoring/build_store.py`:
- computes **per-card IER + mechanic tags** for every card, and
- materializes only the **top-K highest-DER neighbours per card** plus **all Lift pairs** into an indexed
  SQLite store (`cards`, `synergies` with `idx_syn_a/idx_syn_b`).

At request time the backend does pure indexed lookups. DER for an *arbitrary* pair is still `O(1)`: fetch
both cached IERs + tags and apply the formula. The `_candidate_neighbours` seam swaps full-pairwise (dev)
for a **FAISS ANN top-K** query (full scale) without changing anything downstream.

## Components

### `frontend/` — React-first Next.js
Client-rendered builder (`"use client"`): `SearchPanel` → `ZoneColumn`s (dnd-kit droppables) → `StatsSidebar`
(DeckCheck-style gauges, Moxfield-style bracket badge, Deckstats-style curve/pips/hypergeometric). Real card
art via `<img>` from Scryfall's CDN (swap host in `next.config.mjs` once simmander's image host is known).
A Vite SPA is a drop-in alternative — same components.

### `backend/` — FastAPI
`/cards`, `/cards/{id}`, `/score/card/{id}`, `/score/pair`, `/deck/analyze`, `/deck/recommend`. Every read is
`O(1)` against the in-memory card map or the indexed SQLite store. Data sources are env-driven
(`backend/app/config.py`) so dev uses the sample data and prod points at the real simmander DB + score store.

### `scoring/` — offline pipeline
`build_store.py` (CLI, progress bars, logging, Scryfall-tolerant) + `simmander_scoring/` (the IER/CSS/DER/Lift
core, unit-tested, dependency-free).

## Deck analysis (Doc B parity)

`backend/app/analysis.py` produces in one pass: mana curve, color-pip & type distributions, a hypergeometric
playability probability, DeckCheck-style **Efficiency/Impact/Score(1000)** gauges, and a Moxfield-style
**minimum Bracket (1–5)** with the flags that set it (mass land denial, extra turns, fast mana, Lift pairs).

## Integration seams (Phase 0)

| Seam | File | Replace with |
| --- | --- | --- |
| Card source | `backend/app/config.py` (`SIMMANDER_CARDS`) | simmander card DB export |
| Score source | `backend/app/config.py` (`SIMMANDER_SCORES`) | generated store over the full corpus |
| Machine-coded tags | `scoring/simmander_scoring/mechanics.py` | simmander's existing mechanic taxonomy |
| Card image host | `frontend/next.config.mjs` | simmander image host (or keep Scryfall) |
| Deploy | — | simmander-hub conventions (secrets, LFS, CI) |
