# Engine Board — Design Spec (build-ready)

**Date:** 2026-06-11 · **Status:** approved (brainstorm + visual mockup), ready to plan
**Sub-feature D** of the Deck Doctor program. A redesign of the deck-building board into function
"fields" that reveal as you build, split by engine in Composite mode, with multi-modal cards shown in
every field they serve.

## Goal
Make a deck's structure legible at a glance and reward **multi-modal** cards. Each card lands in its
function field as a solid "home" card and appears as a translucent **ghost** in every other field it
also serves. In Simmander Composite mode, each field splits into the two chosen engines (red/blue), and
a card serving both engines gets a 50%-ghost copy in the other half.

## Concepts (locked in brainstorm + mockup)
- **Fields** = the existing zones: Commander, Lands, Ramp, Card Draw, Removal, Board Wipes, Counters,
  Tokens, Utility.
- **Home vs additional (no rank):** every card has exactly one **home** field (its primary
  classification). For every *other* function its tags touch, it shows a ghost marked **"additional"**
  (not "secondary"; all additionals equal, no ordering).
- **Engines (Composite only):** when the active template is **Simmander Composite**, each field splits
  **Engine 1 (left, translucent red) | Engine 2 (right, translucent blue)** with a gilded divider. A
  card sits solid in the engine whose theme it matches; if it also fits the other engine, a **50%-ghost
  copy** appears in that half. Bridging both engines is the desired signal.
- **Progressive reveal:** a field is hidden until at least one card (home or additional) belongs to it.
  Commander is always shown (deck anchor); all others appear as relevant cards arrive.
- **3D tuck:** cards within a field overlap like a fanned pile (CSS transforms), not a flat grid; hover
  raises/fans the pile so you can see tucked cards.
- **250% hover preview:** mousing any card pops it to ~250% as a cursor-following tooltip.
- **Drag:** cards can still be dragged between fields (manual re-home override); ghosts are derived, not
  independently draggable.

## Data derivation — ALL frontend, no backend change
Everything needed already exists client-side: `card.mechanic_tags` + `card.type_line`, and the theme→tag
catalog from `GET /templates` (already loaded into `useTemplateStore.themes`).

- **`lib/functions.ts`** (new):
  - `cardFunctions(card) -> { home: Zone, additional: Zone[] }` — collect EVERY field the card matches
    using the same tag→zone rules as `zones.ts::autoZone` (Land→Lands, `board_wipe`→Board Wipes,
    `removal`→Removal, `ramp`→Ramp, `card_draw`→Card Draw, `counter_*`→Counters, `token_*`→Tokens,
    else Utility). `home` = `autoZone(card)` (the existing single-zone priority pick); `additional` =
    the other matches. Single-function card → empty `additional`. (Refactor `autoZone` to share the
    match list so the two never drift.)
  - `cardEngines(card, themeA, themeB) -> { e1: boolean, e2: boolean }` — `e1` = `card.mechanic_tags`
    intersects the tags of theme A; `e2` likewise for theme B. Theme tag sets come from the loaded
    `themes` catalog keyed by the composite's `themeA`/`themeB` ids. A card matching neither renders
    **neutral** (centered, untinted) within its field.

## Component architecture (`frontend/src/components/`)
Replaces the flat `main` grid of `ZoneColumn`s in `app/page.tsx`.

- **`EngineBoard.tsx`** — orchestrator. From `useDeck` (cards + basics) and `useTemplateStore` (active
  template + composite themes), compute per-field placements: `{ field: Zone, engine1: Card[],
  engine2: Card[], neutral: Card[], ghosts: {card, kind:'additional'|'bridge', engine}[] }`. Render only
  fields with ≥1 placement (+ Commander always). Composite on → split layout; off → single lane per field.
- **`EngineField.tsx`** — one field row: label (name + count) + body. Composite → two `<EnginePile>`
  halves with the gilded divider; non-Composite → one `<EnginePile>`. A drop target (dnd-kit) for
  re-homing.
- **`EnginePile.tsx`** — the tucked 3D stack of `BoardCard`s (overlapping transforms; hover fans/raises).
- **`BoardCard.tsx`** — a single card; `variant: 'solid' | 'ghost'` (ghost = 50% opacity + dashed edge,
  used for both "additional" and engine "bridge"); fires the 250% hover preview; draggable when solid.
- **`HoverPreview.tsx`** — cursor-following 250% card image (extend the existing `CardHoverDetail`).
- `app/page.tsx` swaps `<main>{ZONES.map(ZoneColumn)}</main>` for `<EngineBoard/>`. `ZoneColumn.tsx`
  is retired (or kept behind a flag during rollout).

## Interactions
- **Add a card** → auto-homed to `cardFunctions().home`; its `additional` ghosts + (Composite) engine
  ghosts appear automatically. New relevant fields fade in.
- **Drag** a solid card to another field → re-homes it (overrides `autoZone` for that card; stored as a
  per-card zone override in the deck store, same mechanism as today's `move`). Ghosts recompute.
- **Hover** → 250% preview follows the cursor; the hovered pile fans so tucked cards are visible.
- **Remove** → the card and all its ghosts disappear; a field with no remaining cards collapses
  (re-hidden).

## Composite vs. normal mode
- **Composite active:** split fields (red/blue), engine ghosts, bridge highlighting. If a theme half
  isn't chosen yet (composite themeA/themeB empty), that side has no engine match, so cards render
  **neutral** (centered, untinted) until the user picks themes — the split frame still shows.
- **Any other template / default:** single-lane fields (no split, no engine ghosts) — the home/additional
  ghosting still applies. Switching templates re-renders without touching deck data.

## Visual language (frontend-design — keep the amber/jewel/Cinzel deck)
Red engine `rgba(239,68,68,…)`, blue engine `rgba(59,132,246,…)`, gilded divider (reuse the
TemplatePanel divider gradient), ghosts at 50% opacity with a dashed amber edge, tucked piles with soft
drop shadows, a short staggered fade when a field first appears. Validated mockup:
`.superpowers/brainstorm/<session>/content/engine-board-layout.html`.

## Testing
- **Unit** (`lib/functions.ts`): a multi-function card → correct `home` + `additional`; a single-function
  card → empty `additional`; a both-theme card → `{e1:true,e2:true}` (bridge); neither-theme → neutral.
  (Add a vitest runner if none exists, else assert via Playwright.)
- **Playwright:** add cards of several functions → fields reveal progressively → solid home + ghost
  additional render in the right fields → a multi-function card appears in 2+ fields → switch to
  Simmander Composite → fields split red/blue → choose two themes → a both-theme card shows the bridge
  ghost in the other half → hover pops the 250% preview → removing the card collapses an emptied field.

## Out of scope (v1)
Manual drag into a specific engine half (engine membership stays theme-derived); per-card manual
"additional" tagging; deep pile-reorder UX; mobile/touch tuning; animation polish beyond the basics.
Depends on no other sub-feature, but pairs naturally with A (saved decks) once both land.
