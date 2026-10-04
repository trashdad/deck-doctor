# Deck Doctor — Session Handoff (current: 2026-10-04, late)

> Everything below the line "Historical handoff" is the **June 10** handoff and is stale
> (it predates the Postgres migration, the VPS deploy, the Arcade theme, Card Upgrade Finder).

## Where things run (owner decision 2026-10-04)

- **Production:** simtrack (tracker VPS). `deckdoctor-api` (uvicorn 127.0.0.1:8002),
  `deckdoctor-web` (Next standalone :3001, served from `/opt/deck-doctor/releases/current`),
  `deckdoctor-refresh.timer` (04:30 UTC, scrape → load → rebuild → reload; corpus 85,598 decks),
  `deckdoctor-backup.timer` (03:30 UTC, pg_dump → tower **and** restic → callisto).
  nginx blocks live in **simmander-tracker `nginx/nginx.conf`** (auto-applied).
  SSH: `ssh trashdad@simtrack` (Tailscale SSH). App at `/opt/deck-doctor`, Python 3.10.
- **Deploy:** `ssh trashdad@simtrack 'cd /tmp && sudo /opt/deck-doctor/deploy/deploy.sh [ref]'` —
  builds an immutable web release, restarts, health-checks, **auto-rolls back**. Pushing to `main`
  does not deploy. Full runbook: `deploy/DEPLOY.md`.
- **Development:** legion (this Windows laptop; low RAM — build/verify on simtrack instead).
  Machine roles: `simmander-hub/docs/machine-roles.md`.

## Local dev on legion

```bash
# Postgres 16 (portable). Password auth; credentials in %APPDATA%\postgresql\pgpass.conf.
C:/simmander/pg/pgsql/bin/pg_ctl.exe -D C:/simmander/pg/data -l C:/simmander/pg/server.log start
cd backend && python -m pytest -q        # needs that DB; pure tests (test_upgrade, test_cuts_unit) don't
cd scoring && python -m pytest -q
cd frontend && npx tsc --noEmit && npm run build
cd backend && python -m uvicorn app.main:app --port 8001     # + cd frontend && npm run dev
```
The local DB is the **June snapshot (~5k decks)**; prod has ~85k. Restore a prod dump before
judging recommendation quality (`deploy/DEPLOY.md` → Backups → Restore).

## State on 2026-10-04 (end of the verify-then-deploy session)

- **Live = `main`** (everything below is deployed; release dirs under `/opt/deck-doctor/releases/`).
  Deployed 23:47 UTC (`3cc4e57` → `164a9cd`, 43 s, API blip ~10 s), docs/backup follow-up after.
- **Shipped:** Card Upgrade Finder (PR #2), admin guard (`f8d0c85`), **precon Tune-up (PR #3,
  merged as `8898b0f`)**, fixes `e0b90e9`, `deploy/deploy.sh` + `deploy/backup.sh` (`164a9cd`).
- **Bugs found on a copy of prod data and fixed (`e0b90e9`, TDD):**
  1. `/deck/combos` "one card away" offered off-identity pieces (mono-R Krenko → Food Chain,
     Hullbreaker Horror) and banned ones (Sway of the Stars). Filtered before the 50-cap.
  2. `suggest_cuts` used EDHREC *synergy* only → **Tune-up said "cut Sol Ring" first** (also
     Arcane Signet, Orcish Bowmasters, Blasphemous Act). Now `max(synergy, inclusion)`.
  3. Tune-up offered downgrades (Talisman of Dominance → Pristine Talisman, −0.9 IER). A swap must
     now beat the target on IER or commander synergy.
- **Fixed ops:** `public/*.svg` 404 (releases now include `public/` + `.next/static`); backups go
  off-site to callisto (`rest:…@callisto:8000/simmander/deck-doctor`, first snapshot `51fbd15d`,
  restore-tested) as well as tower; refresh/frontload scripts are executable in git.
- **Verified live:** 5 real corpus decks (Wise Mothman precon-ish, Atraxa, Krenko, Edgar, Prosper)
  through every deck endpoint via the public API — 0 colour-identity/banlist violations; p50
  latency: sweep ~0.7 s, complete ~0.9 s, recommend ~0.5 s, card-upgrade ~0.1 s. Browser: Tune-up
  panel renders on a real deck, 0 console errors.

## Open — owner decisions

- **Combo catalogs on the VPS.** Prod's nightly rebuild has no `COMBO_CATALOG`/`KNOWN_COMBOS`
  → **0 asserted combos** since June (Spellbook's 88k combos unaffected). With the simmander
  repo's `data/combo_catalog.json` + `known_combos.json` (49 KB, private repo) a staging rebuild
  got 96 and all tests pass; without them `scoring` golden tests (2) and
  `test_engine_completion_surfaces_missing_piece` fail on prod data. Ship the files to the box and
  set the env in `deckdoctor-refresh.service`?
- **IER blind spots** surface in upgrades: alternative / Phyrexian costs aren't understood
  (Snuff Out → Soul Rend "+6.8 IER", Dismember → Nim Replica). Needs an IER model fix.
- **Alerting:** a backup failed silently for ~4 months. The tracker's generic
  `simmander-alert@%n.service` could be attached (`OnFailure=`) to `deckdoctor-backup`/`-refresh`.
- **Callisto retention:** the rest-server is append-only — schedule `restic forget --prune` for
  `/simmander/deck-doctor` on callisto (~100 MB/snapshot stored before dedup).
- **Secrets in world-readable unit files** (`DATABASE_URL` in api/refresh/backup units, 0644) →
  move to an `EnvironmentFile` (0600).
- Static `BANLIST` in `suggest.py` disagrees with the Scryfall data the card pool was filtered by
  (e.g. Sway of the Stars, Biorhythm, Lutri are in the June pool). Decide the source of truth.

## Known issues (unchanged)
Mobile unusable; card art defaults to novelty printings; card pool frozen Jun 9 (`data/cards.json`,
`scoring/prep_cards.py` has Windows-only paths); `db.query` swallows DB errors; no CI; ESLint not
configured. Finish plan: `simmander-hub/docs/plans/2026-10-04-revival-brief.md` §5 (and the Fable
plan in the hub, if present).

---

# Historical handoff (2026-06-10)


> **⭑ STATUS: SP1–SP11 ALL SHIPPED.** The full product is built, tested, and verified.
> - SP6 deck persistence/import/export · SP7 Commander Spellbook combos (87,980 loaded) ·
>   SP8 Deck Doctor (complete→100 + cuts) · SP9 d3-force synergy graph · SP10 eval harness ·
>   SP11 docker deploy. Plus a **live refresh pipeline** (`tools/refresh_loop.py` +
>   `POST /admin/reload`) that scrapes → rebuilds → hot-reloads the store with zero downtime.
> - **Tests:** 43 backend + 92 scoring green; `npm run build` clean.
> - **Playwright gate PASSED** (real data): import a list → Combos panel (1 complete +
>   13 one-away) → Doctor complete→100 → apply → Graph (81 nodes/297 edges) → save → cuts.
>   Screenshots in `docs/sp7-combos-panel.png`, `docs/sp9-synergy-graph.png`. Clean reload: 0 errors.
> - **Eval:** engine beats popularity baseline 3.2× on recall@25 (0.276 vs 0.086), 2.3× MRR.
> - **Docs:** comprehensive `README.md` (formulas/diagrams/data-flow), `docs/data-contract.md`
>   updated with all endpoints. Per-phase commits on `main` (still never pushed).
>
> Possible follow-ups: clean-room eval (rebuild co-occurrence excluding eval decks); the
> Caddy reverse-proxy hostname in `deploy/`; push to origin if the user asks.
> (Spellbook crawl is COMPLETE — 91,196 variants scraped, 87,980 combos live.)
>
> Original roadmap: `docs/superpowers/plans/2026-06-10-sp6-sp11-roadmap.md`.
>
> **⭑ OPEN WORK — Maximize the deck corpus, newest-first.** Goal: scrape **as many decks as
> possible** from the public web, prioritized in **reverse-chronological order** (most recently
> *updated* or *built* first) so the corpus skews toward the current meta. Today's `runner.py seeds`
> discovers by commander via EDHREC deckpreview — NOT date-ordered. Add a recency-driven mode:
> - **Archidekt:** its deck-search API supports recency ordering (`orderBy=-updatedAt` /
>   `-createdAt`, paginated ~100/page — verify exact params next session). Walk newest→oldest,
>   fetch each via the existing `_fetch_archidekt`, append (dedup-by-deck_id makes it incremental +
>   resumable; save the last page/cursor for `--resume`).
> - **Moxfield:** browse/search sorted by `updatedAtUtc` desc (Cloudflare-gated → fall back to the
>   EDHREC deckpreview path where blocked).
> - **EDHREC deckpreview:** keep as the breadth fallback (not date-sortable).
> - New runner subcommand, e.g. `runner.py recent --source archidekt --max N`, walking newest-first
>   until sources exhaust or dedup-hit-rate saturates; reuse the per-host throttling + `.seen_deck_ids`.
> - Wire into `tools/refresh_loop.py` so each cycle pulls the freshest decks first, then
>   load_corpus → rebuild → `/admin/reload`. Run it to completion ("all the decks we possibly can").
>
> **⭑ OPEN WORK — Commander list: popularity-sorted + filter/sort/search.** The Commanders view
> (frontend `SearchPanel.tsx` "Commanders" tab → `GET /cards/commanders`, today sorted by name)
> should default to **most-played first** (deck count descending) and gain filter, sort, and a
> free-text search box.
> - **Popularity source = corpus deck count.** `decks.sqlite` has `decks(deck_id, source, commander)`
>   (commander is a name). At startup, Store loads `_commander_decks: dict[card_id, int]` = count of
>   decks per commander, resolving the commander name → id via `_name_to_id`. Add `config.DECKS_PATH`
>   (default `data/decks.sqlite`); empty/absent → all zero (degrade, never break). Handle partner/pair
>   commanders later — v1 keys on the single `commander` name. `Card` model gains optional `deck_count`.
> - **Endpoint:** `GET /cards/commanders?q=&colors=&sort=popularity|name|ier&limit=` — `q` = name
>   substring (free-text), `colors` = color-identity subset filter (reuse existing WUBRG buttons),
>   default `sort=popularity` (deck_count desc, tiebreak name); enrich each with `deck_count`.
> - **Frontend (SearchPanel Commanders tab):** default popularity order; a free-text input; a sort
>   dropdown (Popularity / Name / Efficiency-IER); reuse the color-pip filter buttons; show
>   `{deck_count} decks` on each commander tile. Keep react-query keyed on q+colors+sort.
> - Verify with Playwright: list opens most-played first; typing filters; switching sort reorders;
>   color filter narrows; deck counts render.
>
> **⭑ OPEN WORK — Template System + Dual-Theme Composite.** Fully researched + decided, NOT yet
> coded. Build-ready spec: `docs/superpowers/specs/2026-06-10-template-system-design.md` (exact
> template numbers incl. Command Zone 38/10/8/8/4 + variants + data-derived Corpus Average; the
> verified theme→tag catalog; backend `templates.py` + `GET /templates` + `POST /deck/theme-suggest`
> + `DeckRequest.template`→Doctor; frontend header dropdown + `TemplatePanel` dual-theme editor +
> theme card grid with "Show 10 more"). Locked: both published+data-derived templates; template
> drives Doctor completion; theme cards ranked efficiency+synergy. frontend-design skill applies
> (keep the existing amber/jewel/Cinzel language — two themes as facing "spell pages").

> **UPDATE (2026-06-10, later session):** Both pending items below are DONE.
> 1. The scrape finished and the rebuild ran: decks.sqlite **4,255** decks, edhrec.sqlite
>    **355 commanders / 94,970 rows**, card_cooccurrence **97,598** pairs, relationships re-fused.
> 2. SP5 + SP4 are **implemented and shipped** (plan: `docs/superpowers/plans/2026-06-10-sp5-sp4-beta.md`),
>    plus a Suggestions panel UI. Senior redesign deltas vs. the specs: accumulation scoring
>    (O(|D|·K) not O(|D|²·K)), in-memory engines index (replaces per-request full scan in
>    `deck_engines`), name→id resolution incl. `//` front faces, static banlist in `suggest.py`.
>    Verified: 24 backend + 88 scoring tests pass, `npm run build` clean, full Playwright pass
>    (explorer all 5 axes, pair inspect, pivot/breadcrumb, add; suggestions tier=EDHREC w/ reasons).
> Remaining ideas: graph view of relationships; type-aware suggestion balancing; weight tuning UI.

Self-contained handoff for resuming in a fresh session / different model. Repo:
`C:\simmander\simmander-deckbuilder` (its own git repo, **on `main`**, **49 commits ahead of
`origin/main`, never pushed**). Sibling repos: `C:\simmander\simmander` (card data + machine-coded
cards + combo catalogs), `C:\simmander\simmander-hub` (deploy infra).

The deckbuilder runs a **synergy program** of sub-projects, each with a `spec → plan → build` cycle
under `docs/superpowers/`. Backend = FastAPI on **:8001**; frontend = Next.js on :3000 (proxies
`/api` → :8001); offline pipeline = Python 3.13 **stdlib-only** in `scoring/`; query store =
`data/scores.sqlite` (gitignored, 292 MB, rebuilt from pipelines).

---

## ⚠️ TWO THINGS ARE PENDING RIGHT NOW

### 1. Background scrape running → then DO THE REBUILD (user-requested)
A decklist scrape is running in the background: `python tools/scrape_decklists/runner.py seeds
--top 400 --decks-per 40 --max-commanders 400 --batch run2` (was PID 39580; logs at
`tools/scrape_decklists/run2.log`; launched as background task `b3sinmk0l`). Corpus has grown to
~4,300 deck records in `data/decklists/*.jsonl`, while `data/decks.sqlite` is **frozen at 3,877**
(the SP3 build snapshot).

**The user asked: "let it finish then refresh the DBs and rebuild."** When the scrape process is no
longer running, do EXACTLY this (order matters — `build_relationships` DROPs+recreates
`card_relationships`, so it must precede `build_cooccurrence`):

```bash
cd C:/simmander/simmander-deckbuilder
# 1. refresh both corpus DBs from the grown JSONL
python tools/scrape_decklists/load_corpus.py
# 2. rebuild SP1 relationships (resets card_relationships to structural synergy)
python scoring/build_relationships.py --db data/scores.sqlite \
  --catalog C:/simmander/simmander/data/combo_catalog.json \
  --catalog C:/simmander/simmander/data/known_combos.json
# 3. rebuild SP3 co-occurrence + re-fuse synergy over the larger corpus
python scoring/build_cooccurrence.py --scores data/scores.sqlite \
  --decks data/decks.sqlite --edhrec data/edhrec.sqlite --min-support 20
```
Then spot-check deltas (deck count, `card_cooccurrence` pair count) and report. Verify the scrape is
actually stopped first: `powershell "(Get-CimInstance Win32_Process -Filter \"name='python.exe'\" |
? { $_.CommandLine -match 'runner.py seeds' }).ProcessId"` → empty = finished.
Optional: re-run the scoring suite (`cd scoring && python -m pytest -q`) — golden bounds were set
with generous margins to survive corpus growth.

### 2. SP4 + SP5 specs written, AWAITING USER REVIEW (then writing-plans)
Two new specs are committed but **not yet reviewed or planned**. Per the brainstorming cycle: user
reviews spec → `superpowers:writing-plans` → `superpowers:subagent-driven-development`. Do NOT start
implementation before the user approves each spec.

---

## Program status

| # | Sub-project | Status |
|---|---|---|
| SP2 | Card fingerprint | **Done/merged.** `scoring/fingerprints/`, tables `card_fingerprints`/`card_fingerprint_flat`. |
| SP1 | Relationship measurement | **Done/merged.** `scoring/relationships/`, `scoring/build_relationships.py`, tables `card_relationships` (similarity/synergy_ab/ba/anti_synergy/combo + SP3's `structural_synergy_ab/ba`) + `engines`. |
| — | Semantic Finder | **Done/merged** (commit `1ea602b`). Tag pipeline `scoring/tag_taxonomy.py`+`build_semantics.py`; frontend `SemanticFinder.tsx` etc.; real 30k-card `data/cards.json`. |
| SP3 | Decklist co-occurrence | **Done/merged** (merge `592d1b9`). See below. |
| **SP5** | Commander suggestion engine | **Spec written, awaiting review.** `docs/superpowers/specs/2026-06-10-commander-suggestions-design.md`. Backend-only. |
| **SP4** | Relationship explorer UI | **Spec written (draft), awaiting review.** `docs/superpowers/specs/2026-06-10-relationship-explorer-design.md`. Depends on SP5's `Store` neighbor reads. |

### SP3 recap (just completed this session)
- **Acquisition (delegated):** `tools/scrape_decklists/` — `runner.py` (per-host-throttled `seeds`
  driver: EDHREC deckpreview discovery + Archidekt/Moxfield fetchers), `load_corpus.py`
  (JSONL → two gitignored DBs), `PROMPT.md`. The scraper computes NO statistics — it emits raw decks.
- **Two corpus DBs (gitignored, rebuilt by `load_corpus.py`):** `data/decks.sqlite`
  (`decks`, `deck_cards`) and `data/edhrec.sqlite` (`edhrec_metrics`: commander→card synergy/inclusion).
- **Deterministic mining:** `scoring/cooccurrence/{corpus,mine,edhrec,fuse}.py` + orchestrator
  `scoring/build_cooccurrence.py` → `card_cooccurrence` table (**86,806 pairs**) and re-fuses SP1
  `synergy_ab/ba` via `fuse()=1−(1−structural)·exp(−(0.6·lift_norm+0.4·edhrec))` (exact
  identity-when-empty; structural snapshot kept in `structural_synergy_ab/ba`).
- **Backend:** `cooccurrence` block on `/score/pair`.
- **Tests:** 88 scoring + 10 backend pass.
- **⚠️ KEY FINDING:** SP1 structural pairs and SP3 co-occurrence pairs are **largely disjoint** —
  only ~196 of ~201k structural edges also have lift>1, so fusion enriches few `synergy` values. The
  real value lives in the `card_cooccurrence` table itself (queryable per pair). **SP4 and SP5 read
  `card_cooccurrence` directly** rather than relying on fused synergy. This is why SP5/SP4 are
  designed around the raw tables.

---

## SP5 spec — key decisions (for the reviewer)
Online (read-time) backend engine; no offline build. `Store` loads `data/edhrec.sqlite` in-memory at
startup (resolve names→ids via its card map). Scoring blend over candidate cards:
`w_edh·edhrec_synergy + w_cooc·mean_liftnorm + w_struct·mean_synergy + w_engine·engine_completion`
(defaults 0.45/0.30/0.15/0.10). Candidate gen = union of indexed neighbor lookups (never all 30k).
**Tiered cold-start** for the ~2000 commanders without EDHREC data: EDHREC → commander's own
co-occurrence/synergy neighbors → color-identity-filtered deck-frequency staples. Filters: color
identity ⊆ commander CI, not-in-deck, Commander-legal. Upgrades the stub `POST /deck/recommend`
(legacy DER-based, no frontend consumer — replace cleanly). Per-suggestion reasons (`?explain=true`).
New: `backend/app/suggest.py` + tests; additive changes to `store.py`/`config.py`/`main.py`/`models.py`.

## SP4 spec — key decisions (for the reviewer)
Side-panel relationship explorer with four typed axes: **Similar** (SP1 `similarity`), **Synergizes**
(SP1 directional `synergy_ab/ba`), **Played with** (SP3 `lift`), **Combos** (SP1 `engines`). Inline
pair-inspect via existing `/score/pair`. Graph-walk pivoting + breadcrumb; click-to-add. **Evolves**
the legacy semantic-tag `CardLookupPanel` → `RelationshipExplorer.tsx` (the old TF-IDF "similar" is
kept as a *separately-labeled* axis so the two "similar" notions aren't conflated). Ranked lists per
axis (no force-directed graph in v1). Reuses SP5's `Store` neighbor reads (`synergy_neighbors`,
`cooccurrence_neighbors`, `engines_with`) + thin GET wrappers. Build SP5 first (or SP4 adds the reads
and SP5 reuses — same code either order).

---

## How to run / verify
```bash
# backend (port 8001)
cd backend && python -m uvicorn app.main:app --port 8001
# frontend (port 3000, proxies /api -> 8001)
cd frontend && npm run dev
# tests
cd scoring && python -m pytest -q     # 88 pass
cd backend && python -m pytest -q     # 10 pass
cd frontend && npm run build          # type-check + prod build
```
⚠️ **Stale-server lesson:** kill servers by the port-owning PID, not a process-name filter, or an old
process keeps serving. SQLite `*.sqlite-shm`/`-wal` sidecars are gitignored — never commit them.

## Git state
On `main`, 49 commits ahead of `origin/main` (`git@github.com:trashdad/simmander-deckbuilder.git`),
**never pushed**. This session's work (Semantic Finder, SP3, SP4/SP5 specs) is all committed locally
to `main`. Push only if the user asks. Gitignored: `data/*.sqlite(+sidecars)`,
`data/decklists/*.jsonl` (except `sample.jsonl`), `data/cards.json` is **committed** (21 MB, user's
explicit choice).

## Memory
Persistent memory at `C:\Users\insan\.claude\projects\C--simmander\memory\`; index `MEMORY.md`.
Most relevant: `project_deckbuilder_semantic_finder.md` (program state — keep it updated).
