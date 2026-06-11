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
- **Layout (corrected after mockup v2):** the **commander sits ABOVE** the board in its own strip — it
  is not a field. In **Simmander Composite** mode the board is **two engine columns — Engine 1 (left,
  translucent red) | Engine 2 (right, translucent blue)** with a gilded divider; the function fields
  appear as **tinted subsections nested INSIDE each engine** (Ramp / Card Draw / Removal / … as red
  subsections in Engine 1, blue subsections in Engine 2). In any non-Composite template there are no
  engine columns — just a single column of field subsections (commander still above).
- **Engine placement:** a card is **solid** in the engine whose theme it matches, in its home field's
  subsection. When it matches **both** engines, Engine 1 holds the solid copy and a **50%-ghost "bridge"
  copy** appears in Engine 2's matching subsection. A card matching **neither** theme goes to a
  **neutral section** (full-width, below the two engine columns) carrying the same field subsections.
- **Progressive reveal:** a field subsection is hidden until at least one card belongs to it (within its
  engine). An engine column shows only its non-empty subsections; the neutral section appears only if
  some card matches no theme. The commander strip is always present (prompts to add one).
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

## Placement algorithm (the core derivation)
For each non-commander card in the deck, with `fns = cardFunctions(card)` and (Composite)
`eng = cardEngines(card, themeA, themeB)`:

- **Composite mode:**
  - `solidEngine` = 1 if `eng.e1` (matches theme A), else 2 if `eng.e2`, else **neutral**.
  - Emit **solid** at `(solidEngine, fns.home)`.
  - Emit **additional ghost** at `(solidEngine, f)` for each `f` in `fns.additional` (same engine, other
    function subsections).
  - If `eng.e1 && eng.e2`, emit a **bridge ghost** at `(2, fns.home)` (the other engine, home field).
- **Non-Composite mode:** one lane — emit solid at `fns.home` and additional ghosts at each
  `fns.additional`; no engines, no bridge.

The board groups these into `column → fieldSubsection → { solid: Card[], ghosts: {card,kind}[] }`,
renders only non-empty subsections, and only shows the neutral column when something lands there.

## Component architecture (`frontend/src/components/`)
Replaces the flat `main` grid of `ZoneColumn`s in `app/page.tsx`.

- **`EngineBoard.tsx`** — orchestrator. Reads `useDeck` (cards + basics) + `useTemplateStore` (active
  template + composite `themeA`/`themeB`), runs the placement algorithm, and renders: a
  `<CommanderStrip>` on top, then — Composite → `<EngineColumn engine=1 red>` + `<EngineColumn engine=2
  blue>` + (if any) a neutral `<EngineColumn>` below; non-Composite → a single `<EngineColumn>` with no
  tint/engine.
- **`CommanderStrip.tsx`** — the commander(s) above the board (gilded strip); empty-state prompts to add one.
- **`EngineColumn.tsx`** — one engine (red/blue/neutral): header (engine name + theme) + its non-empty
  field subsections as `<FieldSection>`s.
- **`FieldSection.tsx`** — one function subsection within an engine: label (name + count) + a
  `<CardPile>`; a dnd-kit drop target for re-homing a dragged card into this field.
- **`CardPile.tsx`** — the tucked 3D stack of `BoardCard`s (overlapping transforms; hover fans/raises).
- **`BoardCard.tsx`** — a single card; `variant: 'solid' | 'ghost'` (ghost = 50% opacity + dashed amber
  edge + a small "additional"/"bridge" label, per mockup v2); fires the 250% hover preview; draggable
  when solid.
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
- **Composite active:** two engine columns (red / blue) each with its function subsections; engine
  bridge ghosts; neutral column below for theme-less cards. If a theme isn't chosen yet (themeA/themeB
  empty), nothing matches that engine, so cards fall to the **neutral** column until themes are picked —
  the two empty engine columns still frame the board.
- **Any other template / default:** a single column of field subsections (no engine columns, no engine
  bridges) — the home/additional ghosting still applies. Switching templates re-renders without touching
  deck data.

## Visual language (frontend-design — keep the amber/jewel/Cinzel deck)
Red engine `rgba(239,68,68,…)`, blue engine `rgba(59,132,246,…)`, gilded divider (reuse the
TemplatePanel divider gradient), ghosts at 50% opacity with a dashed amber edge, tucked piles with soft
drop shadows, a short staggered fade when a field first appears. Validated mockup:
`.superpowers/brainstorm/<session>/content/engine-board-layout.html`.

## Testing
- **Unit** (`lib/functions.ts`): a multi-function card → correct `home` + `additional`; a single-function
  card → empty `additional`; a both-theme card → `{e1:true,e2:true}` (bridge); neither-theme → neutral.
  (Add a vitest runner if none exists, else assert via Playwright.)
- **Playwright:** commander shows above the board; add cards of several functions → field subsections
  reveal progressively → solid home + ghost additional render in the right subsections → a multi-function
  card appears in 2+ subsections → switch to Simmander Composite → two engine columns appear → choose two
  themes → cards sort into the matching engine, a both-theme card shows the bridge ghost in the other
  engine, a theme-less card lands in the neutral column → hover pops the 250% preview → removing a card
  collapses an emptied subsection.

## Out of scope (v1)
Manual drag into a specific engine half (engine membership stays theme-derived); per-card manual
"additional" tagging; deep pile-reorder UX; mobile/touch tuning; animation polish beyond the basics.
Depends on no other sub-feature, but pairs naturally with A (saved decks) once both land.
