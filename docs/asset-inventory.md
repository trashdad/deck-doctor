# Phase 0 — Source Asset Inventory

> **Status: PENDING ACCESS.** `trashdad/simmander` and `trashdad/simmander-hub` are private and were not
> readable from the session that scaffolded this repo (GitHub scope was limited to
> `trashdad/simmander-deckbuilder`). This document is the checklist to complete once those repos are added
> to the session scope. Until then the app runs on `data/sample_cards.json` + a locally built score store.

Fill each section in from the real repos, then wire the findings into the seams listed in
[`architecture.md`](architecture.md#integration-seams-phase-0).

## A. `trashdad/simmander` — card database & machine-coded cards
- [ ] **Storage**: Postgres / SQLite / flat files? Connection or export path?
- [ ] **Card schema**: primary key (Scryfall `id`/`oracle_id`?), fields available, naming.
- [ ] **Machine-coded mechanics**: is there an existing mechanic/tag taxonomy? Field name, value set,
      coverage. → replaces / seeds `scoring/simmander_scoring/mechanics.py`.
- [ ] **Existing scoring/value fields**: any precomputed power/efficiency we should feed into IER instead of
      the heuristic?
- [ ] **Card art**: image URIs (Scryfall?) or self-hosted assets? Host + path pattern → `next.config.mjs`.
- [ ] **Corpus size & format**: confirm ~32k cards, Scryfall-format compatibility for `build_store.py`.
- [ ] **Simulator hooks**: anything reusable from the simulator for goldfish/probability features.

## B. `trashdad/simmander-hub` — infrastructure
- [ ] **How simmander.app is served/deployed** (host, container, reverse proxy, domain routing) → how the
      deckbuilder gets "tacked on".
- [ ] **Secrets management** (shared secrets layout) → backend env vars / DB creds.
- [ ] **Git LFS config** → for any large bundled artifacts (score store, image cache).
- [ ] **CI conventions** → mirror for this repo's tests/build.
- [ ] **Multi-machine docs** → where the offline scoring pipeline is expected to run.

## C. Wire-up tasks (after A & B)
- [ ] Point `SIMMANDER_CARDS` / `SIMMANDER_SCORES` (`backend/app/config.py`) at real assets.
- [ ] Prefer simmander's mechanic tags in `mechanics.py`; keep the text scan as fallback.
- [ ] Run `build_store.py` over the full corpus; validate row counts & lookup latency.
- [ ] Confirm card-art host in `next.config.mjs`.
- [ ] Add deploy config per hub conventions; integrate under simmander.app.
