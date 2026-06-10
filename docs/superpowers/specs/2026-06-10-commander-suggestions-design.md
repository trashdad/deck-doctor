# SP5 — Commander-based Suggestion Engine: Design Spec

**Date:** 2026-06-10
**Status:** Approved design, pre-implementation
**Sub-project:** SP5 of the deckbuilder synergy program

---

## Program context

The payoff sub-project: given a commander (and optional partial deck), rank the best cards to
add, blending every signal the program has built. Unlike SP1/SP2/SP3 (offline builders), **SP5 is
an online, read-time engine in the backend** — it queries the prebuilt tables per request, does
no offline build of its own.

| # | Sub-project | Status / relation to SP5 |
|---|---|---|
| SP2 | Card fingerprint | Done. |
| SP1 | Relationship measurement | Done. SP5 reads `card_relationships` (structural synergy) + `engines`. |
| SP3 | Decklist co-occurrence | Done. SP5 reads `card_cooccurrence` (lift) + `edhrec.sqlite` (commander→card). |
| **SP5** | **Suggestion engine (this spec)** | online blend → upgrades the `/deck/recommend` stub. |
| SP4 | Relationship explorer UI | Separate; the suggestions **panel** that surfaces SP5 lives in SP4 (this spec is backend-only). |

The existing `POST /deck/recommend` is a legacy stub (ranks by the old `synergies`/DER table) with
**no frontend consumer**, so SP5 replaces its internals cleanly.

---

## 1. Goal & success criteria

**Done when:** `POST /deck/recommend` returns a ranked list of suggested cards for a given commander
(+ optional partial deck), each with a **reason breakdown**, correctly:

- Blends EDHREC commander→card synergy, co-occurrence lift, structural synergy, and engine/combo
  completion (§3).
- **Filters** out cards already in the deck, cards outside the commander's color identity, and
  Commander-illegal cards.
- **Cold-starts gracefully** for commanders without EDHREC data (§4) — never returns empty for a
  legal commander with a non-trivial deck.
- Never scores all ~30k cards — candidates come from indexed neighbor lookups (§5).
- Backend tests pass: a known-commander golden, the cold-start path, color-identity filtering, and
  the engine-completion bonus.

**Explicit non-goals:** the suggestions UI (SP4); changing the offline pipelines; learned weights;
non-EDH formats; "build me a whole deck" autocompletion (this is next-card ranking, not deck gen).

---

## 2. Data access (no new offline build)

The backend `Store` already loads `scores.sqlite` (cards, `card_relationships`, `engines`,
`card_cooccurrence`). SP5 adds:

- **EDHREC at startup:** `Store` opens `data/edhrec.sqlite` (new `config.EDHREC_PATH`, default
  `data/edhrec.sqlite`) once and builds an in-memory
  `_edhrec: dict[commander_id, dict[card_id, {synergy, inclusion}]]`, resolving the table's
  NAME-keyed rows to ids via the card map it already holds. ~34k rows — trivial in memory. If the
  file is absent, `_edhrec` is empty and the engine cold-starts everywhere (degrades, never breaks).
- **Indexed neighbor reads** on `scores.sqlite` (read-time, O(neighbors)):
  - `cooccurrence_neighbors(card_id, limit)` → `[(other_id, lift, jaccard)]` from `card_cooccurrence`
    (indexed `(a, lift DESC)`; query both `a=?` and `b=?`).
  - `synergy_neighbors(card_id, limit)` → `[(other_id, synergy)]` from `card_relationships`.
  - `engines_with(card_id)` → engines/combos whose member set contains `card_id`.

---

## 3. The scoring model

For a candidate card `c`, commander `cmd`, current deck set `D`:

```
score(c) =  w_edh    · edhrec_synergy(cmd, c)            # commander-conditioned signature
          + w_cooc   · mean( liftnorm(c, d) for d in D ) # plays-well-with the current list
          + w_struct · mean( synergy(c, d)  for d in D ) # mechanical synergy with the list
          + w_engine · engine_completion(c, D)           # c is the missing piece of a near-complete engine/combo
```

- `liftnorm` reuses SP3's `fuse.lift_to_norm` (lift→[0,1)); `synergy` is SP1's directional
  `synergy_ab/ba` oriented deck→candidate; `edhrec_synergy` clamped to [0,1] (SP3's convention).
- `engine_completion(c, D)`: for each engine/combo where `D` already contains all-but-one member and
  `c` is that member, add a bonus (asserted combos weighted higher than structural-candidate engines).
- Default weights `w_edh=0.45, w_cooc=0.30, w_struct=0.15, w_engine=0.10`, hand-tuned against the
  golden set; documented and tunable (learned weights are a non-goal).
- `inclusion` is **not** a primary term (it's dominated by basics — Swamp ≈ 0.99); it's used only as
  a tie-breaker / weak prior, never to rank signature cards.

Empty deck (commander only): the `cooc`/`struct`/`engine` terms are 0, so ranking is pure EDHREC
synergy — exactly the "signature cards for this commander" list, which is the right cold-open.

---

## 4. Cold-start tiers (commanders without EDHREC data — the real concern)

~129 commanders have EDHREC rows; ~2000 legendary creatures don't. Tiered fallback, evaluated in
order, so a legal commander with a non-trivial deck always gets useful suggestions:

1. **EDHREC-seeded:** `cmd ∈ _edhrec` → full blend (§3).
2. **Co-occurrence-seeded:** `cmd ∉ _edhrec` → drop the `w_edh` term; seed candidates from the
   **commander card's own co-occurrence + synergy neighbors** (the commander is itself a card in
   `card_cooccurrence`), plus neighbors of deck cards.
3. **Color-staple fallback:** if tiers 1–2 yield too few candidates (e.g. a brand-new/obscure
   commander with an empty deck), fill from **color-identity-filtered top cards by global
   deck-frequency** (the "format staples in your colors"), computed once from `card_cooccurrence`
   support / a `cards` deck-frequency rollup. Clearly labeled as a generic fallback in the reason.

The active tier is recorded per response so the caller knows the signal quality.

---

## 5. Candidate generation (tractable)

Candidate set = union of, capped per source:
- EDHREC cards for `cmd` (if any),
- `cooccurrence_neighbors` of each deck card (and of `cmd`),
- `synergy_neighbors` of each deck card,
- `engines_with` members for each deck card (the near-complete-engine pieces).

Then filter (color identity ⊆ commander CI; not in `D`; Commander-legal) and score §3. This bounds
work to O(|D| · neighbors), never the full card pool. Color identity comes from the `cards` table
(`color_identity`); the Commander banlist is a small static set in `suggest.py` (extensible).

---

## 6. API

`POST /deck/recommend` (replace internals; keep the route + `DeckRequest` body):
```
Request:  { cards: [{id, zone?, quantity?}], commander_id: str|null }
Query:    ?limit=12&explain=false
Response: { tier: "edhrec"|"cooccurrence"|"color_staple",
            suggestions: [ { card: <Card>, score: float,
                             reasons: [ {signal, detail, value} ]   # present iff explain=true
                           } ] }
```
`commander_id` null or not a legendary → 400 (suggestions are commander-scoped). Existing `Card`
shape reused. The legacy `SynergyEdge[]` response is dropped (no consumer); `models.py` gets a
`Suggestion`/`SuggestionResponse`.

---

## 7. Repo changes & non-goals

**New:** `backend/app/suggest.py` (candidate-gen + scoring + tiers + filtering + reasons),
`backend/tests/test_suggest.py`.
**Changed (additive):** `backend/app/store.py` (load `_edhrec`; add the three neighbor-read methods +
a color-staple rollup), `backend/app/config.py` (`EDHREC_PATH`), `backend/app/main.py`
(`/deck/recommend` calls `suggest`), `backend/app/models.py` (`Suggestion`, `SuggestionResponse`).

**Non-goals:** UI (SP4); offline rebuilds; learned weights; deck autocompletion; non-EDH.

---

## 8. Validation

- **Golden suggestion** (`backend/tests`): for an EDHREC commander in the corpus (e.g. Atraxa),
  top suggestions are dominated by its real signature cards (proliferate/+1-+1/superfriends staples),
  not generic basics.
- **Cold-start:** a commander absent from `_edhrec` with a few deck cards still returns non-empty,
  sensible suggestions via tier 2; an obscure commander with empty deck falls to tier 3.
- **Color-identity filter:** no suggestion falls outside the commander's color identity.
- **Engine completion:** seeding a deck with all-but-one piece of an asserted combo surfaces the
  missing piece near the top with an engine-completion reason.
- **Determinism:** ties broken by a stable key (id) so output ordering is reproducible.

---

## 9. Open questions (carried forward)

- Final blend weights + the engine-completion bonus magnitude — tuned against the golden set;
  revisited as the EDHREC corpus grows.
- Whether to expand EDHREC coverage (more commanders scraped) is an acquisition concern (SP3 tooling),
  not SP5; SP5 must degrade gracefully regardless.
- Type-aware balancing (don't suggest only creatures) — deferred; v1 ranks by score within the
  candidate pool and lets the caller/zone placement handle category balance.
