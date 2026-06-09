# SP1 — Relationship Measurement: Design Spec

**Date:** 2026-06-09
**Status:** Approved design, pre-implementation
**Sub-project:** SP1 of the deckbuilder synergy program

---

## Program context

Second sub-project of the deckbuilder synergy program (SP2 — card fingerprint — is
built and merged). SP1 builds the **relationship measurement layer** on top of SP2's
fingerprint. Each sub-project gets its own spec → plan → build cycle.

| # | Sub-project | Status / relation to SP1 |
|---|---|---|
| SP2 | Card fingerprint | **Done/merged.** SP1 consumes its records + `fingerprint_to_vector` seam. |
| **SP1** | **Relationship measurement (this spec)** | typed pair measures + N-card engines |
| SP3 | Decklist acquisition + co-occurrence mining | **Not built.** SP1 defines a fusion seam for it. |
| SP4 | Card relationship explorer UI | Consumes SP1 output. |
| SP5 | Commander-based suggestion engine | Consumes SP1 + SP3. |

---

## 1. Goal & success criteria

From the SP2 fingerprint (no LLM), compute four *distinct, separately-meaningful*
relationship measures plus a multi-card engine model, **added alongside** the existing
IER/CSS/DER (which stay untouched). The new `synergy` is designated **canonical**; CSS/DER
are marked **legacy** (kept for backward-compatibility, not extended).

**Done when:**

- Every scored card **pair** has: `similarity` (0–1), directional `synergy_ab` / `synergy_ba`
  (0–1), `combo` (bool + `combo_id`), `anti_synergy` (0–1).
- A **resource-flow graph** is built from fingerprints and used to (a) compute synergy,
  (b) mine multi-card **engines** offline, (c) flag **combo candidates**, (d) detect engines
  within a given deck online.
- Combos are **asserted only from the catalog**; structural finds are **candidates**
  (review queue), never auto-asserted as infinite.
- Backend returns the typed edge for a pair and an engine/combo summary for a deck, without
  breaking existing endpoints.
- Golden relationship fixtures + a catalog-recall sanity check pass.

**Explicit non-goals:** SP3 co-occurrence data & fusion weights (seam only); improving IER;
the UI (SP4); auto-asserting structural combos.

---

## 2. Background: current state

- **`synergies` table** (`data/scores.sqlite`): `(card_a, card_b, css, der, lift)`, 247,780
  rows = top-K CSS neighbours per card + Lift pairs. Built by `scoring/build_store.py` using
  the **legacy regex tagger** (`simmander_scoring/mechanics.py`), *not* the SP2 fingerprint.
- **`scoring/simmander_scoring/evaluate.py`**: `isolated_efficiency_rating` (IER),
  `combinatorial_synergy_score` (CSS, from `COMPLEMENTARY_PAIRS` + shared parasitic +
  jaccard), `dynamic_efficiency_ratio` (DER = IER_a + IER_b + IER_a·CSS), `has_lift`.
- **SP2 fingerprint** (merged): `card_fingerprints` / `card_fingerprint_flat` tables,
  `fingerprints.derive.fingerprint_to_vector(records) -> dict[str,int]`, plus derived flat
  tags. Per-effect axes available: `verb, object, scope, quantifier, targeted, counter,
  amount`, plus ability `kind / trigger / cost`.
- **Combo catalogs** (in the `simmander` sibling repo): `data/combo_catalog.json` (50
  Commander-Spellbook combos — 40 two-card, 10 three-card; `pieces`, `result`, `steps`,
  `source_url`) and `data/known_combos.json` (small curated set; `pieces`, `effect`).

CSS today is a crude single number. SP1 upgrades both the **inputs** (fingerprint, not regex
tags) and the **model** (four typed measures + engines).

---

## 3. Design decisions (with rationale)

| Decision | Choice | Rationale |
|---|---|---|
| Output model | **Augment**: keep IER/CSS/DER, add four typed measures | Nothing downstream breaks; migrate consumers gradually. New `synergy` is canonical; CSS/DER legacy. |
| Combo detection | **Hybrid**: catalog asserts, structural heuristic flags candidates | Zero false "infinite" claims; safe coverage growth. |
| N-card | **Full engine detection** | Capture true 3+ card engines (value > sum of pairs), not just pairwise. |
| Engine search | **Hybrid**: offline mining + deck-scoped online | Global "missing piece" suggestions *and* deck-time precision, kept tractable by seeding from the pairwise graph. |
| Anti-synergy v1 | **Conservative rule-based** anti-pattern set | Structural anti-synergy is weak; the strong signal is negative co-occurrence (SP3). Keep v1 precise, small, extensible. |

**Documented ambiguity (from the augment choice):** two "synergy" numbers now exist — legacy
`css` and the new `synergy`. The spec designates `synergy` canonical; `css`/`der`/`lift`
are retained read-only for legacy consumers and not recomputed by SP1.

---

## 4. The four typed pair measures

All computed from the SP2 fingerprint. `similarity` and `synergy` are **different axes**:
two ramp rocks are highly *similar* but barely *synergistic*; a token-maker + an aristocrat
payoff are highly *synergistic* but not *similar*. Keeping them separate is the point.

| Measure | Range | Computation |
|---|---|---|
| `similarity` | 0–1 | cosine (or weighted Jaccard) over `fingerprint_to_vector(a)` vs `(b)`. High = "does the same job" → redundancy / draw-consistency. Symmetric. |
| `synergy_ab`, `synergy_ba` | 0–1 each | resource-flow match (§5): A **produces** resource R that B **consumes / pays off**. Asymmetric by construction. Strength = weighted count of matched resources × magnitudes, squashed to 0–1. |
| `combo` | bool + `combo_id`\|null | catalog lookup (asserted) **or** candidate flag from the engine miner (not asserted; `combo_id=null`, `candidate=true`). |
| `anti_synergy` | 0–1 | conservative rule-based anti-pattern set over fingerprint condition/resource axes (e.g. "rewards empty hand" + "refills hand"; symmetric/punisher effects benefiting opponents; "no-creatures" payoff + creature-heavy). Small & precise in v1; strong signal arrives via SP3 negative co-occurrence. |

Squashing: a monotonic map (e.g. `1 - exp(-k·raw)`) so scores are comparable 0–1; `k`
calibrated against the golden set (§8).

---

## 5. Resource-flow graph (shared substrate)

One directed graph; the single substrate for synergy, engines, and combo candidates.

**Node:** each card → `{produces: set[Resource], consumes: set[Resource]}`, each tagged with
magnitude/quantifier where the fingerprint provides it.

**Resource taxonomy** (derived deterministically from fingerprint verb/object/scope/counter):
```
mana, token, counter:+1/+1, counter:-1/-1, card(draw), gy_card, life,
untap, sacrifice_fodder, death_event, attack_trigger, spell_cast,
landfall, lifegain_event, etc.
```
Examples:
- **produces:** `AddMana`→mana · `CreateTokens`→token · `PutCounter(plus1)`→counter:+1/+1 ·
  `DrawACard`→card · effects that kill creatures→death_event · `GainLife`→life ·
  `UntapPermanent`→untap.
- **consumes / payoff:** trigger "whenever a creature dies"→death_event · "for each token"→
  token · sacrifice outlet→sacrifice_fodder · `cost:tap`→untap · "whenever you gain life"→
  lifegain_event.

**Edge** A→B exists iff `A.produces ∩ B.consumes ≠ ∅`; `synergy_ab` = weighted overlap.
Seeded by generalizing the existing `COMPLEMENTARY_PAIRS` into a full producer→consumer
resource map (`scoring/relationships/resources.py`).

---

## 6. N-card engines + combo (use the graph)

- **Engine** = a connected subgraph (chain or cycle) of size k∈[2..5] where outputs feed
  inputs and **set value > sum of pairwise edges** (the non-additive bonus is the engine
  signal). `kind ∈ {chain, cycle}`.
- **Offline mining** (`engines.py`): seed from high-`synergy` pairs → expand graph neighbours
  up to k=5 → prune (require resource feed-through, cap candidates per seed, dedupe by member
  set) → store engines.
- **Combo candidate** = an engine whose cycle has *unbounded net resource gain* (e.g.
  untap→mana→recast→untap). → review queue; stored with `candidate=true`, **never asserted**.
- **Asserted combos** (`combo.py`): ingest `combo_catalog.json` + `known_combos.json`
  (matched to card ids by name via the SP2 `norm_name` join) → `combo_id, result, steps, url`.
- **Online deck-scoped** detection: for a deck (≤100 cards) build its subgraph and search
  engines/combos within it → powers "your deck completes engine X" / "one piece short."

---

## 7. Storage & API (augment — nothing breaks)

- `synergies` (legacy CSS/DER/Lift): **unchanged**, not recomputed by SP1.
- **New `card_relationships`**: `(a TEXT, b TEXT, similarity REAL, synergy_ab REAL,
  synergy_ba REAL, anti_synergy REAL, combo INT, combo_id TEXT, candidate INT,
  PRIMARY KEY(a,b))`, indexed `(a, synergy_ab DESC)` and `(b, synergy_ba DESC)`.
- **New `engines`**: `(engine_id TEXT PRIMARY KEY, members TEXT/*json card-id list*/,
  kind TEXT, resources TEXT/*json*/, score REAL, asserted_combo INT, candidate INT)`.
- New package `scoring/relationships/`: `resources.py` (fingerprint→resources),
  `graph.py` (build graph), `measures.py` (the four pair measures), `engines.py` (mining +
  deck-scoped search), `combo.py` (catalog ingest + candidate flag). Orchestrator
  `scoring/build_relationships.py` (mirrors `build_fingerprints.py`).
- Backend: `/score/pair` gains the typed edge (existing css/der fields preserved); deck-level
  engine/combo summary folded into `/deck/analyze` (or new `/deck/engines`); `/deck/recommend`
  may rank by `synergy` + engine-completion. All existing fields kept.

---

## 8. SP3 fusion seam + validation

- **Fusion seam:** all scores are structural now. Define
  `fuse(structural_score, cooccurrence_signal) -> final` (default: identity / structural-only
  until SP3 supplies per-pair co-occurrence lift, then a documented blend). SP1 builds the
  seam, **not** the data or the weights.
- **Validation:**
  - **Golden relationships** (`data/golden_relationships/*.json`): hand-verified expectations —
    token-maker + aristocrat → high `synergy`; two removal spells → high `similarity`, low
    `synergy`; a catalog pair → `combo`; a known anti-pattern → elevated `anti_synergy`.
  - **Catalog-recall sanity check:** the engine miner is run against the 50 catalog combos and
    must re-surface a defined majority as candidates (precision/recall sanity; reported, with a
    floor as the gate).
  - **Determinism:** all outputs sorted/stable for persisted JSON and rows.

---

## 9. Repo changes & non-goals

**New:** `scoring/relationships/{resources,graph,measures,engines,combo}.py`,
`scoring/build_relationships.py`, tables `card_relationships` + `engines`,
`data/golden_relationships/`, backend endpoint additions, tests
(`scoring/tests/test_rel_*.py`).

**Changed:** backend `store.py` / `main.py` (load + expose the new tables/edge), additively.

**Non-goals (other sub-projects / future):** SP3 co-occurrence data + fusion weights (seam
only); IER redesign; UI (SP4); auto-asserting structural combos; learned (vs rule-based)
synergy weighting.

---

## 10. Open questions (carried forward)

- Final `synergy` squash constant `k` and the per-resource weights — calibrated against the
  golden set during implementation; revisited once SP3 co-occurrence exists.
- Anti-synergy rule set will start small; expansion is expected ("we might make more later")
  and is additive.
- Engine-miner pruning thresholds (k cap, candidates-per-seed) — tuned against tractability +
  the catalog-recall check.
