# SP4 — Card Relationship Explorer UI: Design Spec

**Date:** 2026-06-10
**Status:** Draft design (awaiting review) — depends on SP5's backend neighbor reads
**Sub-project:** SP4 of the deckbuilder synergy program

---

## Program context

The human-facing window into everything SP1–SP3 computed. SP1/SP2/SP3 produce the data; SP5 uses
it to *suggest*; **SP4 lets a person explore it** — pick a card, see its typed relationships across
every axis, walk the graph, inspect any pair, and add cards to the deck.

**Why it's needed:** the rich data is currently invisible. The existing `CardLookupPanel`
("Cards Most Similar" / "Best Combos") is wired to the **legacy semantic-tag** endpoints
(`/cards/{id}/similar` = TF-IDF over flat tags; `/cards/{id}/combos` = `_COMPLEMENT_PAIRS`), *not*
`card_relationships` (SP1) or `card_cooccurrence` (SP3). `/score/pair` exposes the real typed edge
but nothing renders it. SP4 fixes that.

**Dependency:** SP4 reuses the read methods SP5 adds to `Store` (`synergy_neighbors`,
`cooccurrence_neighbors`, `engines_with`). Build SP5 first. (If SP4 is built first, it adds those
methods itself and SP5 reuses them — same code, either order.)

---

## 1. Goal & success criteria

**Done when:** from any card the user can open a **Relationship Explorer** that shows, for that
focal card, its neighbors across four typed axes — and can inspect any pair's full edge, pivot to a
neighbor, or add a card to the deck.

- Four axes, each backed by **real SP1/SP3 data** (not the legacy semantic-tag methods):
  - **Similar** — SP1 `similarity` (does-the-same-job / redundancy).
  - **Synergizes** — SP1 directional `synergy_ab/ba` (what this enables / what enables it).
  - **Played with** — SP3 `card_cooccurrence` `lift` (empirically run together).
  - **Combos** — SP1 `engines` (asserted combos + candidate engines containing the focal card).
- **Pair inspect:** selecting a neighbor reveals the full typed edge from `/score/pair`
  (similarity, synergy_ab/ba, anti_synergy, combo, co_count/lift) — the "why are these related" readout.
- **Pivot:** clicking *focus* on a neighbor re-roots the explorer on that card (graph walk).
- **Add:** any tile can be added to the deck.
- Each axis shows its driving metric on the tile (e.g. lift = 3.2, synergy 0.61) and an empty-state
  when a card has no neighbors on that axis.

**Explicit non-goals:** the suggestion engine (SP5); a force-directed graph visualization (v1 is
ranked lists per axis — graph view is a possible follow-up); editing/curating relationships;
changing any offline pipeline.

---

## 2. Backend (thin reads over existing tables)

Reuse SP5's `Store` methods; add thin GET wrappers (all O(neighbors), indexed):

- `GET /cards/{id}/relationships?axis=similar|synergy|cooccurrence&limit=30`
  → `[{card, metric}]` where `metric` is the axis value (similarity / oriented synergy / lift).
  Backed by `synergy_neighbors` (card_relationships, ordered by the axis column) and
  `cooccurrence_neighbors` (card_cooccurrence, ordered by lift). "similar" orders by `similarity`.
- `GET /cards/{id}/combos-engines` → `[{engine_id, kind, members:[card…], asserted, candidate}]`
  from `engines_with` (resolves member ids → Card stubs).
- **Pair inspect** uses the existing `GET /score/pair?a&b` (already returns `relationship` +
  `cooccurrence` blocks) — no new endpoint.

The legacy `/cards/{id}/similar` (semantic-tag TF-IDF) is **retained** as a distinct "semantically
similar" lookup (different, still-useful axis); SP4's "Similar" axis uses SP1 `similarity`. Both
coexist; the explorer labels them distinctly so the two notions of "similar" aren't conflated.

---

## 3. Frontend

**Evolve** the existing side panel rather than build a parallel one. `CardLookupPanel` +
`cardLookup` store become the **Relationship Explorer**:

- **Chrome:** the existing right-side panel (`w-[440px]`, amber/jewel theme) — keep it.
- **Header:** focal card name + art thumbnail + its IER.
- **Axis tabs:** `Similar · Synergizes · Played with · Combos`. Switching tabs fetches that axis
  (cached per focal card). Each tab renders a 3-col `CardTile` grid; each tile shows the axis metric
  as a small badge (lift / synergy / similarity / "combo").
- **Pair inspect:** clicking a neighbor tile (not its add button) expands an inline **edge readout**
  at the top of the grid — a compact table of the `/score/pair` values between focal and neighbor
  (similarity, synergy →/←, anti-synergy, co_count, lift, combo flag), each with a one-line gloss.
- **Pivot:** each tile has a *focus* affordance (the existing CardMenu's pattern) → re-roots the
  explorer on that card, pushing the previous focal onto a small back-stack (breadcrumb).
- **Add:** the existing per-tile "＋ Add to deck" overlay (from the Semantic Finder work) is reused.
- **Entry points:** `CardMenu`'s existing items are repointed — "Cards Most Similar" → explorer on
  the *Similar* axis, "Best Pairing / Combos" → *Combos* axis; add a "Played with" item → *Played
  with* axis. The Semantic Finder ("Find by tags") stays separate.

New/changed frontend: `RelationshipExplorer.tsx` (replaces `CardLookupPanel.tsx`), `relationship`
store (replaces `cardLookup`), `lib/api.ts` clients for the new endpoints, `CardMenu.tsx` repointing.
`lib/types.ts` gains the edge/neighbor types.

---

## 4. Data flow

```
CardMenu (focus a card on an axis)
   → relationship store.open(card, axis)
   → GET /cards/{id}/relationships?axis=…   (or /combos-engines for Combos)
   → grid of neighbor tiles (metric badge)
        click tile → GET /score/pair?a=focal&b=neighbor → inline edge readout
        focus tile → store.open(neighbor, sameAxis)   (pivot; push breadcrumb)
        add tile   → deck.add(neighbor)
```

All reads are O(1)/O(neighbors) against indexed tables — no model inference, consistent with the
app's "live site reads precomputed scores" principle.

---

## 5. Validation

- **Backend:** each axis endpoint returns real, correctly-ordered neighbors for a known card
  (e.g. a token-maker's *Synergizes* axis surfaces aristocrat payoffs; a staple's *Played with*
  axis surfaces high-lift partners); `combos-engines` returns engines containing the card; bad/absent
  ids → empty list, not error. Mirror existing `backend/tests/test_api.py` style.
- **Frontend:** `npm run build` type-checks; a Playwright smoke (consistent with the Semantic Finder
  verification) — open the explorer, switch all four axes, inspect a pair, pivot once, add a card —
  each step shows real data.
- **No-conflation check:** the SP1 "Similar" axis and the legacy semantic-tag lookup are visibly
  distinct in the UI.

---

## 6. Repo changes & non-goals

**New:** `frontend/src/components/RelationshipExplorer.tsx`, `frontend/src/store/relationship.ts`,
`backend/app/` GET wrappers (in `main.py`), tests.
**Changed (additive/replacement):** `backend/app/store.py` (the neighbor reads — shared with SP5),
`frontend/src/lib/api.ts` (+clients), `frontend/src/components/CardMenu.tsx` (repoint entries),
`frontend/src/app/page.tsx` (mount explorer in place of `CardLookupPanel`), `lib/types.ts`.
Remove `CardLookupPanel.tsx` + `cardLookup.ts` once the explorer replaces them.

**Non-goals:** force-directed graph view; SP5 engine; relationship editing; offline changes;
non-EDH.

---

## 7. Open questions (carried forward)

- Whether to keep the legacy semantic-tag "similar/combos" lookups long-term or retire them once the
  SP1/SP3 axes prove better — keep both in v1, labeled distinctly; revisit after use.
- Graph/force-directed visualization of the relationship neighborhood — deferred; v1 is ranked lists
  per axis, which is simpler and reads cleanly in the side panel.
- Pair-inspect depth (how many of the typed fields to surface, and their glosses) — start with the
  full set; trim if it reads as cluttered during the Playwright pass.
