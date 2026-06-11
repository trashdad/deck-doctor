# Deck Doctor

**The card-art Commander (EDH) deckbuilder at [simmander.app/deck-doctor](https://simmander.app/deck-doctor) — a deck
editor with a recommendation engine that finds synergies, combos, and card relationships
*before* you do.**

You pick a commander, drop cards into category lanes, and the app instantly tells you: *which
cards to add next, which to cut, which two-card combos you're one card away from completing, and
how the whole deck hangs together as a web of synergies.* Every answer comes back in
**microseconds** because all the heavy thinking is done **offline, ahead of time** — the live
website just looks up pre-computed numbers.

This README explains the whole machine in plain language, with the exact math and diagrams behind
the recommendation engine, and shows how a fleet of non-LLM web scrapers continuously feeds real
human decklists into that engine so the advice keeps getting smarter on its own.

---

## Table of contents

1. [The 60-second mental model](#1-the-60-second-mental-model)
2. [The big picture: how data flows](#2-the-big-picture-how-data-flows)
3. [The four signals (what the engine actually knows)](#3-the-four-signals)
4. [The recommendation formula, step by step](#4-the-recommendation-formula)
5. [Cold start: what happens for obscure commanders](#5-cold-start-tiers)
6. [The Deck Doctor: completion & cuts](#6-the-deck-doctor)
7. [Combos: the Commander Spellbook brain](#7-combos)
8. [The synergy graph](#8-the-synergy-graph)
9. [The scrapers: where the knowledge comes from](#9-the-scrapers)
10. [Seamless updates: how new data changes your recommendations](#10-seamless-updates)
11. [Does it actually work? (evaluation)](#11-does-it-actually-work)
12. [Architecture, repo layout & running it](#12-architecture--running-it)
13. [Feature history (SP1–SP11)](#13-feature-history)

---

## 1. The 60-second mental model

Think of the app as a **library with a card-recommendation librarian**.

- The **library** is a set of databases: ~31,000 Magic cards, ~4,300 real human decklists, EDHREC's
  community statistics, and ~88,000 known card combos.
- The **librarian** (the *scoring pipeline*) reads the whole library **once, offline**, and writes
  index cards: "card A goes well with card B (here's a number)", "these two cards are basically
  interchangeable", "these three cards form a combo." This is slow (minutes) but happens in the
  background.
- The **website** never reads the library directly. It only reads the librarian's index cards,
  which are tiny and instant to look up. So when you add *Sol Ring* to your deck, the site answers
  "here are 24 cards that pair with what you have" in the blink of an eye — no AI is "thinking" at
  request time.

```
   SLOW & OFFLINE                         FAST & ONLINE (microseconds)
   ┌───────────────────┐                  ┌────────────────────────┐
   │  read everything  │  ── writes ──▶   │  look up index cards   │
   │  compute synergy  │   index cards    │  blend a few numbers   │
   │  (the librarian)  │                  │  (the website)         │
   └───────────────────┘                  └────────────────────────┘
```

> **Why no live AI?** A full table of "how good is every card with every other card" is
> 31,000 × 31,000 ≈ **960 million** pairs. You can't compute that per click. So we pre-compute the
> useful slices and store them in indexed SQLite tables that answer in O(1). The site stays
> instant and cheap, and works without a GPU.

---

## 2. The big picture: how data flows

Everything is a one-way river from raw public data on the left to your screen on the right.

```
  PUBLIC SOURCES            ACQUISITION              CORPUS DBs            OFFLINE SCORING                 QUERY STORE             LIVE SITE
  (non-LLM scrapers)        (tools/)                 (data/*.sqlite)      (scoring/)                      (data/scores.sqlite)    (backend + frontend)

  ┌───────────┐            ┌──────────────────┐     ┌──────────────┐     ┌───────────────────────┐       ┌─────────────────┐     ┌──────────────┐
  │  EDHREC    │──┐         │ scrape_decklists │     │ decks.sqlite │     │ build_relationships.py│       │ cards (IER,     │     │ FastAPI      │
  │ (stats +   │  │         │   runner.py      │────▶│  4,255 decks │────▶│  → similarity,        │──┐    │   tags)         │     │  :8001       │
  │  decklists)│  ├────────▶│ (per-host        │     │              │     │    synergy, engines   │  │    │ card_relation-  │     │              │
  ├───────────┤  │ JSONL    │  throttled,      │     ├──────────────┤     ├───────────────────────┤  ├───▶│   ships 201,893 │────▶│ /deck/recom- │
  │ Archidekt  │──┤ append-  │  resumable,      │     │ edhrec.sqlite│     │ build_cooccurrence.py │  │    │ card_cooccur-   │     │   mend       │     ┌──────────┐
  │  (deck API)│  │ only     │  parallel        │────▶│ 354 cmdrs    │────▶│  → lift, jaccard,     │──┘    │   rence 97,598  │     │ /deck/combos │────▶│ Your     │
  ├───────────┤  │          │  workers)        │     │ 94,970 rows  │     │    fused synergy      │       │ engines 35,028  │     │ /deck/complete│    │ browser  │
  │  Moxfield  │──┘          └──────────────────┘     └──────────────┘     └───────────────────────┘       └─────────────────┘     │ /deck/graph  │     │ :3000    │
  └───────────┘                                                                                            ┌─────────────────┐     │ /deck/cuts   │     └──────────┘
  ┌───────────┐            ┌──────────────────┐     ┌──────────────┐                                       │ spellbook.sqlite│     │              │
  │ Commander  │───────────▶│ import_spellbook │────▶│ 87,980 combos│──────────────────────────────────────▶│ (loaded into   │────▶│ Suggestions, │
  │ Spellbook  │  REST/JSON │  runner+load     │     │              │                                       │  memory)        │     │ Combos, Graph│
  └───────────┘            └──────────────────┘     └──────────────┘                                       └─────────────────┘     └──────────────┘

  └──────────────────────────── tools/refresh_loop.py runs this whole river on a timer, then POSTs /admin/reload ───────────────────────────────┘
```

The key databases (all gitignored, rebuilt from the pipelines; sizes as of this writing):

| File | What's in it | Built by |
|---|---|---|
| `data/cards.json` | ~31k Magic cards (Scryfall fields) — *committed* | bundled |
| `data/decks.sqlite` | 4,255 real human decklists (which cards appear together) | `scrape_decklists` |
| `data/edhrec.sqlite` | EDHREC's per-commander card stats (354 commanders, 94,970 rows) | `scrape_decklists` |
| `data/spellbook.sqlite` | 87,980 curated two-to-six-card combos | `import_spellbook` |
| `data/scores.sqlite` | the **query store**: per-card power, card↔card relationships, co-occurrence, engines | `scoring/build_*.py` |

---

## 3. The four signals

The engine forms an opinion about "should I add card *c* to this deck?" by blending **four
independent signals**. Each answers a different question. Here's what each one is and how it's
computed.

### Signal 1 — IER (Isolated Efficiency Rating): "is this card good *on its own*?"

A single number, roughly 1–20, for each card's raw power in a vacuum — derived from its mana cost,
the card advantage it generates, and its stats. It is **not** used to rank suggestions directly
(a powerful card isn't necessarily right for *your* deck), but it shows on every card tile and
breaks ties.

### Signal 2 — Co-occurrence lift: "do real decks actually run these together?"

This is the empirical heart of the system. We scraped 4,255 real decks. For any two cards A and B
we ask: **do they appear together more often than random chance would predict?** That's the
classic *market-basket "lift"* from association-rule mining:

```
              P(A and B in the same deck)            observed togetherness
   lift(A,B) = ───────────────────────────   =   ───────────────────────────
                   P(A) · P(B)                     expected if independent

   lift = 1.0  →  they co-occur exactly as often as chance  (no signal)
   lift > 1.0  →  played together MORE than chance          (positive synergy)
   lift = 4.0  →  4× more likely to be together than random (strong pairing)
```

Lift naturally filters out "staple" cards. *Sol Ring* is in almost every deck, so it co-occurs with
everything — but its **lift** with any specific card is near 1.0 (no special bond). Two niche
aristocrat cards that always travel together get a high lift. Raw lift is unbounded, so we squash
it into a tidy 0–1 "lift-norm" with a saturating curve:

```
   liftnorm(lift) = 1 − e^(−0.25 · (lift − 1))     for lift > 1,  else 0

   lift:      1.0   1.5   2.0   3.0   5.0   10.0   ∞
   liftnorm:  0.00  0.12  0.22  0.39  0.63  0.89  →1.0
              │                                    │
              └─ no association          strong ───┘   (diminishing returns; never quite 1)
```

### Signal 3 — Structural synergy: "do their mechanics *fit*, even if no one's tried it?"

Lift only knows what humans have already built. Structural synergy is computed from the cards'
**machine-read rules text** — a producer/consumer match. If card A *creates tokens* and card B
*triggers when a creature enters*, they synergize **mechanically** whether or not any human deck
has paired them yet. This catches brand-new cards and off-meta gems that lift can't see. Stored as
a directional `synergy_ab` / `synergy_ba` (A-enables-B may differ from B-enables-A).

### Signal 4 — EDHREC synergy: "what does the community say defines this commander?"

EDHREC publishes, per commander, a "synergy" score for each card: how much more often that card
shows up in *this commander's* decks versus decks in general. It's the single best signal for "what
are the signature cards for my commander," so it gets the heaviest weight when available.

### Bonus signal — Combos: "does this card *finish* a known game-winning interaction?"

From Commander Spellbook (§7): if your deck already has all-but-one piece of a known combo, the
missing piece gets a large bonus. This is the difference between "a fine card" and "the card that
wins you the game."

---

## 4. The recommendation formula

When you ask for suggestions, the engine scores every *candidate* card `c` against your current
deck `D` (commander included) and ranks them. The score is a weighted blend of the four signals:

```
                w_edh · edhrec(cmd, c)        ← signature card for your commander
              + w_cooc · mean_liftnorm(c, D)  ← real decks run it with your cards
   score(c) = ─────────────────────────────────────────────────────────────────────
              + w_struct · mean_synergy(c, D) ← its mechanics fit your cards
              + w_engine · combo_bonus(c, D)  ← it completes a combo/engine
                                  └─ all divided by (w_edh+w_cooc+w_struct+w_engine) to keep 0–1

   default weights:   w_edh = 0.45   w_cooc = 0.30   w_struct = 0.15   w_engine = 0.10
```

Two design choices make this both *correct* and *fast*:

**(a) The means are computed by accumulation, not pairwise.** The naive reading of
`mean_liftnorm(c, D)` is "for every candidate, look up its lift with every deck card" — that's
`candidates × |D|` database queries (hundreds of thousands). Instead we walk it the other way:

```
   for each card d already in your deck:                 ← |D| iterations (≈ 60)
       for each of d's top-30 lift neighbours (c, lift): ← one indexed DB read per deck card
           accumulator[c].cooc  += liftnorm(lift)        ← c banks d's contribution
           accumulator[c].hits  += 1
   ...later: each candidate's mean = accumulator[c].cooc / |D|
```

This is **O(|D| × 30)** total reads — a few thousand, not a few hundred thousand. A card never
looked up contributes 0, which is exactly what the mean would give it anyway. Same math, ~100×
fewer queries. The result: suggestions return in ~20–70 ms for a full deck.

**(b) Candidates come from neighbour lookups, never the whole card pool.** We only ever score cards
that are *somebody's* neighbour (an EDHREC card for your commander, a lift/synergy neighbour of a
deck card, or a combo piece). We never iterate 31,000 cards.

### A worked example

You're playing **The Ur-Dragon** with *Sol Ring*, *Command Tower*, *Arcane Signet* in the deck.
The engine considers **Dragon Tempest** as a candidate:

```
   edhrec(Ur-Dragon, Dragon Tempest) = 0.69   (a top signature card)
   mean_liftnorm over your 4 cards    = 0.25   (decent real-deck overlap)
   mean_synergy over your 4 cards     = 0.05   (modest mechanical tie)
   combo_bonus                        = 0.00   (not finishing a combo here)

   score = (0.45·0.69 + 0.30·0.25 + 0.15·0.05 + 0.10·0.00) / 1.00
         = (0.3105 + 0.075 + 0.0075 + 0) / 1.0
         = 0.393                                ← ranks near the top of the list
```

Each suggestion can be returned **with its reasons** (`?explain=true`), which is what the
Suggestions panel shows as little chips: `EDHREC 0.69 · played with 0.25 · …`.

---

## 5. Cold-start tiers

~354 commanders have rich EDHREC data; ~2,000 legendary creatures don't. The engine degrades
gracefully through three tiers so **every legal commander gets useful advice**:

```
   ┌─ Tier 1: EDHREC ─────────────┐   commander has EDHREC rows → full 4-signal blend.
   │                              │
   ├─ Tier 2: CO-OCCURRENCE ──────┤   no EDHREC → drop w_edh; seed candidates from the
   │                              │   commander's OWN lift/synergy neighbours + deck neighbours.
   │                              │
   └─ Tier 3: COLOR STAPLES ──────┘   too few candidates (brand-new/empty deck) → fall back to
                                      the most-played cards in your colour identity. Clearly
                                      labelled "staple" so you know the signal is generic.
```

The active tier is returned with the response and shown as a badge (`EDHREC` / `CO-OCCURRENCE` /
`STAPLES`) so you always know how strong the evidence behind your suggestions is.

---

## 6. The Deck Doctor

Suggestions rank *next cards* but ignore deck **shape** — left alone they'd happily recommend 60
creatures. The Doctor fixes that with two tools.

### Complete my deck → 100 cards, deterministically

It greedily fills the deck toward a sane Commander template, but **boosts whatever category you're
short on** and **caps the categories you've already filled**:

```
   TEMPLATE (of 100):  37 lands · 10 ramp · 10 draw · 9 removal · 3 wipes · ~30 synergy/strategy

   repeat until you have 62 non-land cards:
       pool = top 120 suggestions (the §4 engine)
       for each candidate, boosted = score × (1.5 if its category is under quota else 1.0)
       pick the highest boosted score   ← deficit categories jump the queue
       (skip a candidate whose quota is already full; "synergy" is uncapped overflow)
       every 10 picks, recompute the pool against the growing deck

   then build the mana base:
       • up to 12 non-basic "staple" lands in your colours
       • the rest as basic lands, split by your deck's actual coloured-mana demand:
```

The basic-land split mirrors your real pip counts. If your non-land cards need
`{R}` twice as often as `{U}`, you get twice as many Mountains as Islands:

```
   pips counted from every non-land card's mana cost  →  R: 18, U: 9, G: 3   (total 30)
   25 basic slots × (18/30, 9/30, 3/30)               →  15 Mountain, 7.5 Island, 2.5 Forest
   round; hand out leftovers by largest fraction       →  15 Mountain, 8 Island, 2 Forest  (=25)
```

Everything is deterministic (ties broken by card id) — the same deck always completes the same way.

### Suggest cuts → what's weakest

The mirror image of §4: instead of scoring outside cards *against* your deck, it scores each card
already *in* your deck against the rest of it, and lists the **lowest contributors** first:

```
   contribution(c) = w_edh·edhrec(cmd,c) + w_cooc·mean_lift(c, deck∖c) + w_struct·mean_syn(c, deck∖c)

   cards that real decks rarely run alongside the rest of YOUR deck sink to the bottom.
   (Lands, your commander, and any card that's part of a complete combo are protected from cuts.)
```

In testing, a Dragon deck correctly surfaces generic *Lightning Bolt* and *Sol Ring* as the first
cut candidates — they're powerful but contribute little to *this* deck's web of synergies.

---

## 7. Combos

[Commander Spellbook](https://commanderspellbook.com) is the community's canonical database of
proven combos. We scrape all **87,980** commander-legal combos (each: the cards it needs and what
it produces — "Infinite mana", "Win the game", etc.) into `spellbook.sqlite`.

This powers the product's killer feature, the **Combos panel**, which classifies every combo
against your deck:

```
   ┌─ In your deck ──────────────────────────────────────────────────────┐
   │  Isochron Scepter + Dramatic Reversal → Infinite mana, Infinite      │
   │                                          storm count                 │
   ├─ One card away (the gold) ──────────────────────────────────────────┤
   │  add Hullbreaker Horror  (+ Sol Ring)   → Infinite colorless mana    │
   │  add Narset's Reversal   (+ Isochron…)  → Infinite turns             │
   └──────────────────────────────────────────────────────────────────────┘
```

Combos also feed the recommendation engine: a card that completes a known combo gets the **biggest
single bonus** (`w_engine` with a 1.2 multiplier — higher than any mined engine), so "the card that
wins the game" floats to the very top of your suggestions with a reason chip explaining what it
does.

---

## 8. The synergy graph

The Suggestions and Combos panels show *lists*. The **graph** shows your deck as a *structure*:
every card is a node (coloured by role — green ramp, blue draw, red removal, gold commander…), and
every meaningful relationship is an edge:

```
   edge colour      meaning                         drawn when
   ─────────────    ─────────────────────────────   ────────────────────────────
   magenta (combo)  these cards combo together       part of a complete combo
   gold (synergy)   mechanics fit                     structural synergy ≥ 0.30
   blue (played)    real decks run them together      co-occurrence lift ≥ 2.0
```

A physics simulation (d3-force, drawn on a `<canvas>`) pulls related cards together, so **clusters**
(your token engine, your reanimator package) form visibly, **bridge** cards that tie strategies
together stand out, and **isolated** nodes float to the edge — instant cut candidates. Hover to
highlight a card's connections, drag to rearrange, click to dive into that card's relationships.
A real 99-card deck renders as ~80 nodes / ~300 edges and stays smooth.

---

## 9. The scrapers

The recommendation engine is only as smart as the data behind it, and that data comes from
**non-LLM, deterministic web scrapers** in `tools/`. They do exactly one job — fetch raw public
data and write it down — and compute **no** statistics themselves (all the math lives in
`scoring/`, deterministic and unit-tested). This separation means the scrapers can run cheaply and
continuously without ever touching the scoring logic.

### `tools/scrape_decklists/` — real human decklists

A resumable, polite, **parallel** harness that pulls from three sources:

```
   EDHREC "deckpreview"  ─┐  discovers thousands of real decklists per commander and resolves
                          │  each to its original Archidekt/Moxfield source — the breadth engine,
                          │  without hammering Moxfield's Cloudflare gate.
   Archidekt deck API   ──┤  public JSON; excludes maybeboard/sideboard.
   Moxfield deck API    ──┘  public JSON mainboard + commanders.
   EDHREC commander JSON ──  per-commander card synergy/inclusion stats.
```

Politeness and parallelism are built in: a **per-host rate limiter** (e.g. EDHREC's CDN tolerates
0.3 s between calls; Moxfield gets 1.2 s) lets independent hosts proceed *simultaneously* via a
worker pool, while never overloading any one site. Output is **append-only JSON-lines**, deduped by
deck id, so the corpus only ever grows and re-running is always safe.

```
   runner.py  ──writes──▶  data/decklists/*.jsonl  ──load_corpus.py──▶  decks.sqlite + edhrec.sqlite
   (one deck = one line)    (durable, deduped)        (idempotent)        (query-ready)
```

### `tools/import_spellbook/` — the combo database

A resumable cursor-paginated crawler over the Commander Spellbook REST API (with exponential
back-off on rate limits), writing each combo as a JSON line, then `load_spellbook.py` folds the
commander-legal ones into `spellbook.sqlite`.

---

## 10. Seamless updates

The brief was: *recommendations should change seamlessly as new cards are added and new decks are
built.* This happens in **two distinct senses**, and the app handles both:

### Sense 1 — you add a card to YOUR deck → instant (no rebuild)

The recommendation endpoints recompute **from scratch on every request** against your current deck.
Add *Sol Ring*, and the very next suggestions/combos/graph call already accounts for it — there is
no cache to invalidate, no model to retrain. This is the whole point of the O(1)-lookup design: the
deck is an *input*, not part of the precomputed store.

```
   you add a card  ──▶  React deck state changes  ──▶  panels refetch (react-query)
                   ──▶  engine re-blends the §4 formula over the new deck  ──▶  new advice, ~30 ms
```

### Sense 2 — the world builds new decks → the engine's *evidence base* grows

As more real decks are scraped, the co-occurrence/EDHREC tables get richer, so the *same* deck earns
better-grounded suggestions over time. A continuous daemon keeps this current **without restarting
the server**:

```
   tools/refresh_loop.py  (runs forever, on a timer)
   ┌──────────────────────────────────────────────────────────────────────────────┐
   │ 1. SCRAPE   more decks (EDHREC/Archidekt/Moxfield)   → data/decklists/*.jsonl  │
   │ 2. LOAD     fold JSONL into the corpus DBs           → decks/edhrec.sqlite     │
   │ 3. REBUILD  recompute relationships + co-occurrence  → scores.sqlite           │
   │ 4. RELOAD   POST /admin/reload                       → backend swaps tables    │
   └──────────────────────────────────────────────────────────────────────────────┘
                                                              │
   The backend keeps the query store in memory for speed.    ▼
   /admin/reload drops that in-memory copy so the next request rebuilds it from the
   freshly-written sqlite — new decks are now live, with ZERO downtime.
```

This was demonstrated live during build: the combo database was hot-reloaded from 10,646 → 87,980
combos via a single `POST /admin/reload`, with the server never stopping. Run the daemon alongside
the app:

```bash
python tools/refresh_loop.py --interval 1800     # a refresh cycle every 30 min
python tools/refresh_loop.py --once              # one cycle then exit
python tools/refresh_loop.py --no-rebuild        # scrape+load only (cheap)
```

---

## 11. Does it actually work?

We measure it objectively (`scoring/eval_suggest.py`). The test: take 400 **real** decks the engine
has never been "told" about, **hide 10 cards** from each, hand the engine the rest, and ask it to
reconstruct the missing cards. Then measure how many it recovers.

```
                         the engine        popularity baseline       lift
   recall@25             0.276             0.086                     3.2× better
   MRR                   0.081             0.035                     2.3× better
   recall@10             0.179             —
   recall@50             0.343             —
```

*Recall@25* = "of the 10 hidden cards, what fraction appeared in the engine's top 25 guesses." The
engine recovers **3.2× more** real deck choices than simply suggesting the most popular cards in the
colours — strong evidence it's modelling genuine synergy, not just popularity.

> **Honest caveat (printed by the harness):** the co-occurrence/EDHREC tables were built from these
> same decks, so the absolute numbers are optimistic. They are valid for *relative* comparison
> (engine vs. baseline, weight set A vs. B), which is exactly what we use them for. The harness also
> includes a grid search (`--grid`) that re-tunes the four weights on a train split and reports the
> winner's score on a held-out test split.

---

## 12. Architecture & running it

```
   frontend/   Next.js 14 (App Router, TypeScript) — card-art builder, zones, drag-drop,
               Suggestions / Combos / Doctor / Graph / Decks panels. zustand + react-query + Tailwind.
   backend/    FastAPI on :8001 — every read is an O(1) lookup against the in-memory card map or the
               indexed SQLite store. No model inference at request time.
   scoring/    Offline Python pipeline (stdlib-only) — IER, relationships, co-occurrence, eval harness.
   tools/      The scrapers + the live refresh daemon (stdlib-only).
   deploy/     Dockerfiles + compose for containerised deploy.
   data/       cards.json (committed) + generated sqlite stores (gitignored).
```

The backend is built around a single in-memory `Store` (`backend/app/store.py`) loaded once at
startup: cards, EDHREC stats, engines, co-occurrence neighbours, and the spellbook. Each engine —
`suggest.py` (recommendations), `doctor.py` (completion/cuts), `graph.py` (synergy graph) — is a
thin, pure function over that store.

### Run it locally

```bash
# 1. Backend (port 8001) — needs the prebuilt data/*.sqlite stores
cd backend && pip install -r requirements.txt
python -m uvicorn app.main:app --port 8001

# 2. Frontend (port 3000, proxies /api → :8001)
cd frontend && npm install && npm run dev

# 3. (optional) keep the corpus growing in the background
python tools/refresh_loop.py --interval 1800
```

### Affiliate links

Every card in the app shows **ManaPool ↗** and **TCGplayer ↗** buy links. They work out of the
box — without config they point to bare product pages. To earn commissions, copy
`frontend/.env.local.example` to `frontend/.env.local` and fill in your codes:

| Variable | What it does |
|---|---|
| `NEXT_PUBLIC_MANAPOOL_REF` | ManaPool TapFiliate ref appended to every card URL and the deck-cart handoff |
| `NEXT_PUBLIC_MANAPOOL_PARTNER` | ManaPool partner tag for the `/add-deck` cart URL |
| `NEXT_PUBLIC_TCGPLAYER_IMPACT` | Impact path `ACCOUNT/CAMPAIGN/AD` — wraps TCGplayer links via `tcgplayer.pxf.io` |

### Rebuild the data from scratch

```bash
python tools/scrape_decklists/runner.py seeds --top 400 --decks-per 40   # scrape decks
python tools/scrape_decklists/load_corpus.py                              # → decks/edhrec.sqlite
python scoring/build_relationships.py  --db data/scores.sqlite ...        # → relationships, engines
python scoring/build_cooccurrence.py   --scores data/scores.sqlite ...    # → co-occurrence, synergy
python tools/import_spellbook/runner.py && python tools/import_spellbook/load_spellbook.py  # combos
```

### Tests

```bash
cd backend && python -m pytest -q     # 43 API/engine tests
cd scoring && python -m pytest -q     # 92 scoring/eval tests
cd frontend && npm run build          # type-check + production build
```

### Deploy

```bash
docker compose -f deploy/compose.yaml up --build   # full stack on :3000 against mounted data/
```

See [`deploy/README.md`](deploy/README.md) for the data-volume contract.

---

## 13. Feature history

The deckbuilder was built as a sequence of self-contained sub-projects, each with a
spec → plan → build cycle under `docs/superpowers/`:

| # | Sub-project | What it added |
|---|---|---|
| SP1 | Relationship measurement | card↔card similarity / synergy / anti-synergy / combo edges |
| SP2 | Card fingerprint | machine-read mechanical signature per card |
| SP3 | Decklist co-occurrence | lift/jaccard from 4,255 real decks, fused with structural synergy |
| — | Semantic Finder | tag-based card search over machine-read abilities |
| SP4 | Relationship explorer UI | five-axis side panel: similar / synergizes / played-with / combos / tags |
| SP5 | Suggestion engine | the four-signal blend (§4) with tiered cold-start |
| SP6 | Deck persistence | save/load/import/export decks (Moxfield/Archidekt/MTGO/Arena formats) |
| SP7 | Commander Spellbook | 87,980 curated combos → completion bonus + Combos panel |
| SP8 | Deck Doctor | type-aware completion to 100 + cut suggestions |
| SP9 | Synergy graph | d3-force visualization of the deck as a relationship web |
| SP10 | Eval harness | objective recall@k / MRR measurement + weight grid search |
| SP11 | Deploy | containerised backend + frontend + compose stack |

The full design specs and implementation plans live in `docs/superpowers/`.
