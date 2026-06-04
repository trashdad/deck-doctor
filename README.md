# Simmander Deckbuilder

The card-art EDH deckbuilder for **[simmander.app](https://simmander.app)** — a robust, clean GUI that
renders real Magic card art and organizes cards into designated category **zones**, backed by an
offline-computed synergy engine that the live site reads in `O(1)`.

This repo is the deck-building front-end of the Simmander ecosystem. It reuses card data and machine-coded
cards from [`trashdad/simmander`](https://github.com/trashdad/simmander) and infrastructure conventions from
[`trashdad/simmander-hub`](https://github.com/trashdad/simmander-hub).

## Architecture

```
frontend/   React-first Next.js 14 (App Router, TS) — card-art builder, zones, drag-drop, stats
backend/    FastAPI — card search, deck analysis, O(1) score lookups, recommendations
scoring/    Offline Python pipeline — IER / CSS / DER + Lift -> query-ready SQLite store
data/       Sample cards + generated score store (scores.sqlite is gitignored)
docs/       Architecture, data contract, and the Phase-0 asset inventory
```

Data flow: `simmander` card DB → `scoring/` offline pipeline → `data/scores.sqlite` →
`backend/` FastAPI (`O(1)` reads) → `frontend/` React GUI.

See [`docs/architecture.md`](docs/architecture.md) for the full design and the scoring vocabulary
(IER / CSS / DER + Lift).

## Quick start

```bash
# 1. Build the offline synergy store from the sample cards
cd scoring
pip install -r requirements.txt        # optional accelerators; core runs stdlib-only
python build_store.py --cards ../data/sample_cards.json --out ../data/scores.sqlite

# 2. Run the API
cd ../backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 3. Run the GUI
cd ../frontend
npm install
npm run dev        # http://localhost:3000  (proxies /api -> :8000)
```

## Tests

```bash
cd scoring && python -m pytest        # scoring core (IER/CSS/DER/Lift)
cd backend && python -m pytest        # API endpoints
cd frontend && npm run build          # type-check + production build
```

## Status

v1 foundation is in place: scoring pipeline, API, and React GUI all run end-to-end on the bundled sample
data. Integration with the real `simmander` card database and `simmander-hub` deploy infra is **Phase 0**
and gated on read access to those private repos — see
[`docs/asset-inventory.md`](docs/asset-inventory.md) for the exact checklist and the documented seams
(`backend/app/config.py`, `scoring/build_store.py`, `frontend/next.config.mjs`).
