# SP3 — Decklist Acquisition + Co-occurrence Mining: Design Spec

**Date:** 2026-06-09
**Status:** Approved design, pre-implementation
**Sub-project:** SP3 of the deckbuilder synergy program

---

## Program context

Third sub-project of the deckbuilder synergy program. SP2 (card fingerprint) and SP1
(relationship measurement) are built + merged; the Semantic Finder is shipped. SP3 supplies
the **real co-occurrence signal** that SP1 designed a fusion seam for but never received —
upgrading every synergy score from structural-only to data-backed, and unblocking SP5.

| # | Sub-project | Status / relation to SP3 |
|---|---|---|
| SP2 | Card fingerprint | **Done.** SP3 reuses its `norm_name` join for name→id. |
| SP1 | Relationship measurement | **Done.** Documented a `fuse(structural, cooccurrence)` seam (identity default). **SP3 creates that seam in code** and routes `synergy` through it. CSS/DER stay untouched. |
| **SP3** | **Decklist acquisition + co-occurrence (this spec)** | delegated scraping → corpus → deterministic mining → `fuse()` |
| SP4 | Relationship explorer UI | Consumes SP1 (+ SP3's fused scores). |
| SP5 | Commander-based suggestion engine | **Unblocked by SP3** — needs SP1 + SP3. |

---

## 1. Goal & success criteria

From a corpus of **real decklists** plus **EDHREC commander→card aggregates**, compute a
per-card-pair co-occurrence signal and a directional commander→card signal, then **fuse** both
into SP1's canonical `synergy` (CSS/DER untouched, same augment discipline as SP1).

**Done when:**

- A normalized, append-only **decklist corpus** exists (`data/decklists/*.jsonl`), filled by a
  **delegated LLM scraper** (not by this repo's code).
- Deterministic mining produces `card_cooccurrence(a, b, co_count, lift, jaccard, support,
  edhrec_synergy_ab, edhrec_synergy_ba)`.
- A real `fuse()` function exists: identity when no co-occurrence data, a documented monotonic
  blend when present. `card_relationships.synergy_ab/ba` are routed through it.
- Backend exposes the co-occurrence block on `/score/pair`; existing fields preserved.
- Golden co-occurrence fixtures + determinism + a `fuse()` unit test pass.

**Explicit non-goals:** the scraper *running* (delegated); SP4 UI; SP5 suggestions; learned
(vs hand-tuned) fusion weights; computing any statistic inside an LLM.

---

## 2. The two-layer split

Per the acquisition directive, SP3 is two cleanly separated layers joined by a dumb data
contract. The LLM does **only** flaky web work and emits raw data; **all** statistics are
deterministic, tested, reproducible code in this repo.

```
[ Delegated LLM scraper ]  --writes-->  data/decklists/*.jsonl  --read-->  [ this repo's mining ]
  EDHREC / Archidekt /                  (the corpus contract)              counts, lift, fuse(),
  Moxfield  (raw only)                                                     tables, API
```

**Hard rule:** the scraper never computes lift/synergy/anything. If a number needs computing,
it is computed here, from the raw corpus, deterministically.

---

## 3. The corpus contract (the seam)

`data/decklists/*.jsonl` — one JSON object per line, append-only (scraping accrues over time;
mining re-runs over the whole corpus and is idempotent). Two record kinds share the file set:

**Deck record** (raw decklist):
```json
{"kind": "deck", "deck_id": "moxfield:abc123", "source": "moxfield",
 "commander": "Atraxa, Praetors' Voice",
 "card_names": ["Sol Ring", "Cultivate", "Doubling Season", "..."]}
```

**EDHREC aggregate record** (commander→card, pre-aggregated by EDHREC):
```json
{"kind": "edhrec", "commander": "Atraxa, Praetors' Voice",
 "cards": [{"name": "Doubling Season", "synergy": 0.62, "inclusion": 0.71}, "..."]}
```

Rules the scraper must honor: `deck_id` is `source:nativeid` (dedup key); `card_names` excludes
sideboard/maybeboard; names are raw card names (id resolution happens here via SP2 `norm_name`);
unknown cards are dropped at mine time, not by the scraper. Malformed lines are skipped + counted.

---

## 4. Mining (deterministic) — `scoring/cooccurrence/`

| File | Responsibility |
|---|---|
| `corpus.py` | Stream `*.jsonl`, validate, split deck vs edhrec records, normalize names→ids (SP2 `norm_name`), dedup decks by `deck_id`. |
| `mine.py` | From deck records: `df(card)` deck-frequency, `df(a,b)` co-deck count over **support-gated** candidate pairs; **lift** = `P(a,b)/(P(a)·P(b))`, **jaccard** = `df(a,b)/(df(a)+df(b)−df(a,b))`. |
| `edhrec.py` | From edhrec records: directional `edhrec_synergy_ab` where `a` is the commander and `b` a listed card (EDHREC's own synergy score). Naturally maps to SP1's directional `synergy_ab`. |
| `fuse.py` | `fuse(structural, signals) → final` (§5). The seam SP1 only documented. |
| `build_cooccurrence.py` | Orchestrator → writes `card_cooccurrence`, then **re-routes** `card_relationships.synergy_ab/ba` through `fuse()`. |

**Support gating:** only pairs with `df(a,b) ≥ MIN_SUPPORT` (default 20) get a row — below that,
lift is noise. Candidate pairs come from co-membership within decks (never all-pairs). `MIN_SUPPORT`
reported, tunable; the floor is a quality gate, not a silent cap (logged count of dropped pairs).

**Lift normalization:** raw lift ∈ [0, ∞). Squash to [0,1) via a monotonic map (reuse SP1's
`1 − exp(−k·(lift−1)₊)` shape) so it is comparable and fuse-able. Pairs with lift ≤ 1 (no
positive association) contribute 0.

---

## 5. The fuse() seam

Two signals refine SP1's structural `synergy`, by axis:

- **Symmetric** raw-deck co-occurrence (`lift_norm`) → refines both directions equally
  (cards played together a lot).
- **Directional** EDHREC commander→card (`edhrec_synergy_ab`) → refines that one direction
  (commander-context synergy), matching SP1's existing asymmetry.

```
fuse(structural_ab, lift_norm, edhrec_ab) =
    1 − (1 − structural_ab) · exp( −(α · lift_norm + β · edhrec_ab) )
```
This "fill the remaining headroom" form is chosen specifically so identity-when-empty is
**exact**, not approximate (no re-squashing of the already-[0,1] structural value).

- **Identity-when-empty (exact):** with no co-occurrence data `lift_norm = edhrec_ab = 0` ⇒
  `exp(0) = 1` ⇒ `fuse = 1 − (1 − structural_ab) = structural_ab`. Existing scores are bit-for-bit
  preserved when the corpus is empty.
- **Monotonic & bounded:** strictly increasing in `lift_norm` and `edhrec_ab`; always stays in
  `[structural_ab, 1)`. More signal only ever raises the score toward 1.
- `α, β` are documented constants (default α=0.6, β=0.4), calibrated against the golden set;
  learned weights are an explicit non-goal.

`structural_ab` stays available (a `structural_synergy_ab` column is retained on
`card_relationships` so the pre-fusion value is never lost and fusion is reproducible/reversible).

---

## 6. Storage & API (augment — nothing breaks)

- **New `card_cooccurrence`**: `(a TEXT, b TEXT, co_count INT, lift REAL, jaccard REAL,
  support INT, edhrec_synergy_ab REAL, edhrec_synergy_ba REAL, PRIMARY KEY(a,b))`, indexed
  `(a, lift DESC)`.
- **`card_relationships`** (SP1): add `structural_synergy_ab/ba REAL` (pre-fusion snapshot);
  `synergy_ab/ba` become the fused values. Schema additive; CSS/DER/`similarity`/`combo`/
  `anti_synergy` unchanged.
- Backend: `/score/pair` gains a `cooccurrence` block `{co_count, lift, jaccard, support}` and
  keeps everything else. New `Store.cooccurrence(a,b)` mirrors `Store.relationship`.

---

## 7. The delegated scraper artifact

Authored here, executed elsewhere (a local Agent on Legion now; portable to the Chimera LLM
gateway later):

- `tools/scrape_decklists/PROMPT.md` — the scraper's instructions: target sites
  (EDHREC / Archidekt / Moxfield), the §3 corpus contract, rate-limit + ToS rules
  (EDHREC ≥2s/req, cache; respect robots/ToS), dedup by `deck_id`, append-only output, and a
  "compute nothing" rule.
- `tools/scrape_decklists/runner.py` — a thin, resumable harness the delegated LLM drives:
  fetch → parse to corpus records → append to `data/decklists/<source>-<batch>.jsonl`. Stateless
  across runs except the corpus itself + a `seen_deck_ids` file.

This repo's tests **do not** run the scraper. A small committed **sample corpus**
(`data/decklists/sample.jsonl`, a dozen hand-built decks) drives mining tests deterministically.

---

## 8. Validation

- **Golden co-occurrence** (`data/golden_cooccurrence/*.json`): hand-verified expectations against
  the *real* mined table once the corpus is non-trivial — Sol Ring + Arcane Signet → high lift;
  two unrelated off-color cards → lift ≈ 1 (no association); a known commander→staple
  (Atraxa → Doubling Season) → elevated `edhrec_synergy_ab`.
- **`fuse()` unit tests:** identity when signals are 0; strictly increasing in `lift_norm` and
  `edhrec_ab`; output stays in [0,1].
- **Determinism:** sorted/stable rows; mining is idempotent over a fixed corpus (re-run → identical
  table).
- **Sample-corpus integration:** `build_cooccurrence` over `sample.jsonl` produces the expected
  small table and re-fuses `card_relationships` without touching CSS/DER.

---

## 9. Repo changes & non-goals

**New:** `scoring/cooccurrence/{corpus,mine,edhrec,fuse,build_cooccurrence}.py`,
`tools/scrape_decklists/{PROMPT.md,runner.py}`, `data/decklists/sample.jsonl`,
`data/golden_cooccurrence/`, table `card_cooccurrence`, `card_relationships` column additions,
backend `Store.cooccurrence` + `/score/pair` block, tests `scoring/tests/test_cooc_*.py`.

**Changed:** `scoring/relationships/measures.py` or `build_relationships.py` to call `fuse()`
when the co-occurrence table exists (additive; identity when absent). Backend `store.py`/`main.py`
additively.

**Non-goals:** scraper execution (delegated); SP4 UI; SP5; learned fusion weights; any
LLM-computed statistic; cross-format (non-EDH) decks in v1.

---

## 10. Open questions (carried forward)

- Final `α, β` fusion weights and the lift-squash `k` — calibrated against goldens once the real
  corpus is sized; revisited if the corpus grows large enough to support per-pair confidence.
- `MIN_SUPPORT` floor (default 20) — tuned against corpus size; logged, not silent.
- Whether EDHREC aggregate records should also seed *symmetric* lift for high-inclusion staples,
  or remain strictly directional — start directional; revisit if too sparse.
