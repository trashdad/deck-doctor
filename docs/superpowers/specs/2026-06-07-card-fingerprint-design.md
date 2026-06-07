# SP2 — Card Fingerprint: Design Spec

**Date:** 2026-06-07
**Status:** Approved design, pre-implementation
**Sub-project:** SP2 of the deckbuilder synergy program (see "Program context" below)

---

## Program context

This spec is **one sub-project** of a larger effort to rebuild how the deckbuilder
measures and surfaces card relationships. The full effort decomposes into eight
sub-projects, each with its own spec → plan → build cycle:

| # | Sub-project | Depends on |
|---|---|---|
| **SP1** | Relationship measurement framework (similarity/redundancy vs synergy/enabling vs combo vs anti-synergy; metrics for 2..N cards) | SP2, SP3 |
| **SP2** | **Card fingerprint (this spec)** — structured behavioral decomposition of every card | — |
| SP3 | Ethical decklist acquisition + co-occurrence mining | — |
| SP4 | Card relationship explorer UI (link/unlink terms) | SP1, SP2, SP3 |
| SP5 | Commander-based suggestion engine | SP1, SP2, SP3 |
| SP6 | Smart land/mana base selection | (light) |
| SP7 | Commander recommender quiz | (light) |
| SP8 | Affiliate deck export (TCGPlayer + Manapool) | — (leaf) |

SP2 was chosen first: lock the card representation before deciding how to measure
over it. **SP2 stops at "rich, correct, queryable fingerprint + derived views + QA."**
It does **not** define synergy metrics (SP1), the UI (SP4), or decklist data (SP3).

---

## 1. Goal & success criteria

Produce a **deterministic, near-lossless structured behavioral fingerprint** for every
Commander-legal card, built from simmander's MTGish typed corpus (**no LLM**), with
curated derived views for UI and scoring, and a QA harness that proves correctness and
self-surfaces gaps on new sets.

**Done when:**

- Every card has a canonical record (or a *correct empty* record for vanilla cards).
- Records capture trigger, cost, timing, condition, optionality, modality, and
  per-effect `verb / object / scope / quantifier / targeted / amount / duration` — i.e.
  "burn 3 to *each opponent*" is distinguishable from "burn 1 to *one targeted* opponent."
- Golden regression passes; coverage + unmapped-operator reports are green/triaged.
- The flat-tag UI and existing synergy reads keep working, now **derived** from the new canonical.

**Explicit non-goals:** synergy/similarity metrics (SP1); the link/unlink UI (SP4);
decklist/co-occurrence data (SP3). SP2 exposes the *seams* those consume, nothing more.

---

## 2. Background: current state

The pipeline already exists and has been run against the corpus.

- **Corpus:** `data/cards.json` = 30,969 Commander-legal cards (filtered from Scryfall by
  `scoring/prep_cards.py`). MTGish typed corpus: `simmander/mtgish/data/cards.json` =
  32,394 cards parsed into typed operator trees (`_Trigger`, `_Action`, `_CounterType`,
  `_Players`, …), ~98.84% engine coverage upstream.
- **Existing tables in `data/scores.sqlite`:**
  - `card_ability_tags` (53,589 rows): per-ability **flat bag** of tags.
  - `card_flat_tags` (29,756 rows): per-card union — **96.1% coverage**.
  - `tag_inverted_index` (182 rows): tag → card ids, for the finder.
- **Existing code:** `scoring/tag_taxonomy.py` (namespaced tag maps + `TAG_META` display
  metadata), `scoring/build_semantics.py` (walks MTGish, emits the tables above),
  `scoring/prep_cards.py` (Scryfall → commander filter).

### Two measured gaps that motivate this work

1. **No magnitude, no quantifier, lossy combination.** "burn 3 to *each* opponent" vs
   "burn 1 to *one* opponent" both collapse to `e:damage` + a target tag; "-1/-1 on *all*
   creatures" vs "*one* creature" are both `perm:creature`. A multi-effect ability becomes
   one flat bag (`["e:mana","e:roll_dice","perm:creature","tgt:self"]`), so which effect
   binds to which object/amount/scope is lost. There is no `q:` (quantifier) or amount
   namespace at all.
2. **Structural operators are dropped.** Measured against the corpus:
   `_Trigger` 74/381 distinct ops mapped (**~12% of occurrences unmapped**); `_Action`
   113/1411 mapped (**~40% of occurrences unmapped**). The top unmapped action ops are
   *control-flow* nodes — `If`, `Unless`, `IfElse`, `May`, `MayCost`, `EachPlayerAction`,
   `CreateFutureTrigger` — i.e. exactly the condition / optionality / cost / per-player
   structure the fingerprint needs.

### Coverage triage (the "hand-code burden" is small)

Of the 1,213 currently-untagged cards:

| Category | Count | Reality |
|---|---|---|
| Basic/lands, no text | 101 | Legitimately empty — no work |
| Vanilla / no oracle text | 1,038 | Legitimately empty — no work |
| In MTGish but untagged | 22 | Almost all dual/basic lands — small mana-ability mapping gap |
| **Genuine MTGish misses** | **52** | Almost entirely Un-set / acorn joke cards |

The real hand-coding burden is **~50–75 cards**, nearly all silver-border. We exclude
acorn/Un-set cards from the corpus (see §4), driving genuine misses toward zero. **SP2's
real work is the schema enrichment + projector + QA, not coverage.**

---

## 3. Design decisions (with rationale)

| Decision | Choice | Rationale |
|---|---|---|
| Fingerprint shape | **Hybrid**: canonical structured records + auto-derived views | One source of truth; existing UI/scoring keep working while depth is added underneath. |
| Schema depth | **Maximal, near-lossless** projection of MTGish | User priority on fidelity ("no deferrals"); derived views curate down so noise doesn't reach scoring. |
| Coverage | **MTGish primary + hand-code outliers** | Deterministic, no LLM; triage shows the outlier set is tiny. |
| Validation | **Golden regression + coverage report + unmapped-operator report** | Proves correctness *and* completeness; new sets self-surface gaps. |
| Canonical storage | **Normalized schema + retained raw subtree** | Normalized = stable contract for SP1/SP4/SP5; raw = true losslessness + re-mining without re-reading 29 MB. |

### Prior-art validation (deep research, 2026-06-07)

Verified against primary sources (Card-Forge wiki, magefree/mage, CubeArtisan
`magic-card-parser`, Scryfall docs, arXiv 2407.05879; full report archived with the
research run). 17/25 claims survived 3-vote adversarial verification. Outcome: **our
verb/object/scope/quantifier/amount/condition/optionality decomposition is well-aligned
with — and more structured than — the closest analogues.** Six refinements were folded in
(see §4.2). Refuted ideas we deliberately did **not** adopt: Forge's single-letter line
prefixes do *not* cleanly map to our `kind` axis; engine ability-classes do *not* map 1:1
to `kind`; "input representation has little effect" was refuted (representation matters for
the unseen-card/synergy case).

---

## 4. Canonical schema

### 4.1 The per-ability record

One record per ability (`ability_idx`), plus the verbatim MTGish subtree as an escape hatch:

```jsonc
ability_record = {
  ability_idx: 0,
  kind: "triggered" | "activated" | "static" | "spell"
       | "replacement" | "prevention" | "restriction",   // §4.2(3)
  trigger:  { op: "WhenACreatureDies", subject: {...} } | null,
  cost:     { mana: "2B", tap: true,
              sacrifice: { type: "creature", n: 1 }, ... } | null,
  timing:   "sorcery_only" | "instant" | null,
  condition:{ op: "If" | "Unless" | "AsLongAs",
              comparison: { lte: 5 }, value: "life" } | null,   // §4.2(4)
  optional: true | false,                                       // "you may"
  modal:    { choose: 1, up_to: false,
              modes: [ <effect-group>, <effect-group> ] } | null, // §4.2(5)
  effects: [
    {
      verb:       "lose_life",            // named effect token (Forge AB$/DB$ analogue)
      object:     "player",               // affected object TYPE
      prefixes:   ["each"],               // other/another/target/each (CubeArtisan)
      scope:      "each_opponent",        // who/what is actually affected (Forge Defined$)
      quantifier: "each",                 // all | each | single | up_to | n
      targeted:   false,                  // §4.2(1): targets vs affects-without-targeting
      amount:     <amount-expr>,          // §4.2(2)
      duration:   "permanent" | "end_of_turn" | null,
      grants:     "hexproof" | null,      // §4.2(4): innate-vs-granted ability
      sub_effects:[ ...nested effect... ],
      reflexive:  <trigger> | null
    }
  ],
  raw: { /* verbatim MTGish subtree for this ability */ }
}
```

`<amount-expr>` (§4.2(2)):

```jsonc
amount = {
  kind: "literal" | "x" | "dynamic",
  value: 3,                       // present for "literal"
  count: {                        // present for "dynamic" (Forge Count$ / XMage DynamicValue)
    counted_object: "creature",
    zone: "battlefield",
    filter: { controller: "you", attacking: true },
    multiplier: 1,
    cap: null, floor: null
  } | null
}
```

### 4.2 The six research-driven refinements

1. **`targeted` flag, separate from `scope`/`object`.** Forge splits `ValidTgts$` (legal
   targets) from `Defined$` (actually-affected). "Targets one creature" ≠ "affects all
   creatures." Highest-value correction.
2. **`amount` is a composable expression**, not a scalar/string — `{kind, value, count{…}}`
   with `count` carrying `counted_object/zone/filter/multiplier/cap/floor`. Mirrors Forge
   `Count$` and XMage `DynamicValue`; lets SP1 compare/bucket magnitudes by *what they
   scale on*.
3. **`kind` includes `replacement`, `prevention`, `restriction`** as first-class (XMage
   treats these as separate effect categories). We classify by the *effect-side* shape,
   not by engine ability-class.
4. **Innate-vs-granted + conditional are explicit** (`condition`, `grants`, `kind`). The
   `filigree-texts` hexproof case: innate vs conditional vs acquired-via-ability must be
   distinguishable. `condition` uses a comparison-over-value shape (CubeArtisan).
5. **First-class `modal`** (`choose N of M`, `up_to`) and object **`prefixes`**
   (other/another/target/each).
6. **Feature-vector seam is late-fusion-ready** (see §5.3): designed to fuse with SP3's
   co-occurrence embedding, and to stand alone for cold-start (unseen cards).

### 4.3 Storage

New, canonical:

- `card_fingerprints(card_id TEXT, ability_idx INT, record TEXT /*JSON*/,
   source TEXT, confidence REAL, PRIMARY KEY(card_id, ability_idx))`
  - `source ∈ {mtgish, outlier, land_fix}`; `confidence` = 1.0 for mtgish/hand-coded.
- `card_fingerprint_flat(card_id TEXT PRIMARY KEY, record TEXT /*JSON: per-card roll-up*/)`

Existing `card_ability_tags`, `card_flat_tags`, `tag_inverted_index` become **derived
outputs** (§5), regenerated each build — never hand-maintained.

---

## 5. Extraction & derivation pipeline

New package `scoring/fingerprints/`:

```
scoring/fingerprints/
  schema.py     # dataclasses + JSON (de)serialization for ability_record / amount
  project.py    # the projector: MTGish tree -> ability_record
  derive.py     # ability_record -> flat tags, inverted index, feature vector
  qa.py         # golden regression + coverage report + unmapped-operator report
```
`scoring/build_semantics.py` is refactored to orchestrate: project → persist canonical →
derive views → run QA.

### 5.1 The projector (`project.py`)

Replaces the flat `extract_nodes` flatten with a structure-preserving walk:

1. **Recurse through structural operators** (`If`, `Unless`, `IfElse`, `May`, `MayCost`,
   `And`/`Or`, `EachPlayerAction`, `CreateFutureTrigger`) → populate `condition`,
   `optional`, `modal`, per-player distribution, and `sub_effects`, then descend to leaf
   effects. *(This is the ~40%-unmapped action bulk.)*
2. **Leaf maps** (today's `TRIGGER_MAP`/`ACTION_MAP`/`COUNTER_MAP`/`KEYWORD_MAP`/… in
   `tag_taxonomy.py`) name the `verb`/`trigger`/counter/keyword. Extended to add
   **quantifier**, **amount**, `targeted`, and the missing **`c:minus1` / -1/-1** mapping.
3. **Outliers:** the ~50–75 genuine misses are hand-coded in `data/outliers/*.json` using
   the same schema (`source: "outlier"`).
4. **Land mana-ability fix:** the ~22 dual/basic lands that produce no record get their
   intrinsic mana ability projected (`source: "land_fix"`).

### 5.2 Corpus scope change (`prep_cards.py`)

Exclude silver-border / **acorn / Un-set** cards from `data/cards.json` (by
set/security-stamp/legality), driving the genuine-miss set toward zero and keeping the
corpus to cards a serious Commander deckbuilder cares about.

### 5.3 Derived views (`derive.py`) — pure projections of the canonical

- **Enriched flat tags** — today's `t:`/`e:`/`c:`/`k:`/`tgt:`/`perm:`/`r:` **plus new
  namespaces**: `q:` quantifier (all/each/single/up_to), `amt:` magnitude bucket, `cost:`
  (e.g. `cost:sacrifice`), `time:sorcery`, `cond:` (gated), `may:` (optional),
  `tgts:` (targeted). Feeds existing UI chips + `TAG_META` (which gains the new groups).
  *Optional cross-check:* validate/bootstrap this vocabulary against Scryfall Tagger's
  functional (`otag`) slugs.
- **Inverted index** — regenerated for the finder (SP4 consumer).
- **Feature-vector seam** — a documented `fingerprint_to_vector(record) -> dict/array`
  function producing a structured feature vector. **SP1 owns the exact vector shape and
  weighting.** SP2 guarantees the canonical is rich enough to build any reasonable vector,
  and that the seam is **late-fusion-ready** so SP3's co-occurrence embedding can be
  concatenated/fused. The structured vector is the cold-start signal for unseen cards.

---

## 6. Validation / QA harness (`qa.py`)

Three build-time gates:

1. **Golden regression** — `data/golden/*.json`: ~50–100 hand-verified records spanning
   every mechanic family (ETB, dies-trigger, activated w/ cost+timing, modal, replacement,
   X-spell, dynamic-amount, targeted vs each, -1/-1, etc.). Pipeline output must equal
   golden exactly. Guards against projector regressions.
2. **Coverage report** — % cards with non-empty records, verb/trigger/scope distributions,
   empty-record list cross-checked against the vanilla triage (so empties are *expected*).
3. **Unmapped-operator report** — distinct operators present in the corpus **minus**
   operators the projector handles → prioritized, occurrence-weighted gap list. Baseline:
   ~12% trigger / ~40% action occurrences unmapped today. Makes a new set's novel operators
   **fail loudly** instead of silently dropping.

**Acceptance bar:** golden regression must pass (hard gate). Coverage + unmapped-operator
reports are produced every build and must be reviewed/triaged; the unmapped list is a
shrinking backlog, not a hard build failure (so a new set never *blocks* a rebuild, but its
gaps are always visible).

---

## 7. Repo changes & non-goals

**New:** `scoring/fingerprints/{schema,project,derive,qa}.py`, `data/golden/`,
`data/outliers/`, SQLite tables `card_fingerprints` + `card_fingerprint_flat`.

**Changed:** `scoring/build_semantics.py` (orchestrate), `scoring/tag_taxonomy.py` (extend:
quantifier/amount/targeted/`c:minus1`, new `TAG_META` groups), `scoring/prep_cards.py`
(acorn exclusion).

**Unchanged contract:** `card_ability_tags`/`card_flat_tags`/`tag_inverted_index` keep
their shapes (now derived), so the backend/frontend keep working.

**Non-goals (other sub-projects):** synergy/similarity metrics (SP1); link/unlink UI (SP4);
decklist + co-occurrence data (SP3). The feature-vector *shape* and the co-occurrence
*corpus* are explicitly deferred; SP2 only guarantees the seam.

---

## 8. Open questions (carried to SP1/SP3)

- EDHREC / Commander Spellbook actual data model for co-occurrence & combos (corpus for the
  fused vector). Not verified in research; an SP3 question.
- Which fingerprint axes (verb, object/scope, amount bucket, condition, `targeted`, kind)
  are most predictive of synergy — feature weighting/ablation when fusing with the
  co-occurrence embedding. An SP1 question.
- Best Commander co-occurrence corpus to replace card2vec's 17Lands draft data (singleton
  format weighting). An SP3 question.
