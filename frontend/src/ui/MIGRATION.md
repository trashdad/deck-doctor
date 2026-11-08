# UX framework — migration map (phase 0 → 1 → 2)

> **Live workbench is MOUNTED behind a flag (2026-11-06 05:50, tsc-clean, not visually verified).**
> `page.tsx` renders `<WorkbenchLive />` in place of `StatsSidebar` only when `?workbench=1` is in the URL or
> localStorage `dd-workbench` is `"1"` (`?workbench=0` overrides localStorage); default OFF, nothing else in
> `page.tsx` changes (drawer toggles still present). `components/workbench/WorkbenchLive.tsx` composes
> `DeckHeader` + `DoctorRail` from the real deck store and the drawers' endpoints
> (`/deck/analyze` → bracket, `/deck/recommend` → Suggest, `/deck/cuts` → Cuts); it needs no props. Status: Suggest,
> Cuts and Combos tabs are live (`CombosTab` takes `/deck/combos` data via `DoctorRail.combos`, fetched only
> while that tab is showing); header ledger quotas come from `useTemplateStore.activeCounts()` for the five
> doctor categories (Lands/Ramp/Card Draw/Removal/Board Wipes), mapped as `TemplatePanel.CAT_ZONE` does —
> other zones stay `null`. TuneUp tab is live too (`TuneUpTab` takes `/deck/upgrade-sweep` data via
> `DoctorRail.tuneUp`, fetched only while that tab is showing, sharing `useSweepStore` slider/synergy settings;
> the tab has no slider controls yet). Pivot has no endpoint. Old drawers untouched (`UpgradeSweepPanel` still
> renders its own body). (Combos + TuneUp tabs tsc-clean but not visually verified, 2026-11-06 05:53.)
> `ReasonChips` → `ReasonLine` is done in `SuggestionsPanel` and `DeckDoctorPanel` (cuts); `UpgradeSweepPanel`
> (has only `commanderId`, no name) and `CardUpgradePanel` still use `ReasonChips` (exported from `SuggestionsPanel`).

Framework built from `docs/plans/2026-11-05-ux-direction-and-plan.md` §7. The live app is **partly
rewired** (see "Order to swap" below, verified 2026-11-06 05:56 by grep — no build, no browser): the
singletons are mounted, the deck/commander/find cards use `CardInteractive`, and the old components
that remain coexist with the new ones. Gallery: `/deck-doctor/dev/ui-kit`
(`?motion=0` for deterministic screenshots). Tests: `npx playwright test tests/ui-kit.spec.ts`
(projects `ui-kit-desktop`, `ui-kit-laptop`, `ui-kit-mobile`; the dev server starts itself).

## Where things live

| Layer | Files |
|---|---|
| Tokens | `ui/tokens.ts` (Z, TIMING, SIZE, ROLE_HUE) · `ui/tokens.css` (CSS vars, `data-motion="0"`) · `ui/framework.css` (`dd-*` styles) · `tailwind.config.ts` (zIndex, durations, `role.*`, `panel-solid`, `label/body/num` sizes) |
| Hooks | `hooks/usePointerKind`, `useHoverIntent`, `usePopoverPlacement` (pure placement maths, hand-rolled — see below), `useLongPress`, `useRovingFocus`, `useMenuKeyboard`, `useUndoableDeck` (+ `useUndoHotkeys`) |
| Card | `components/card/CardFrame` (visual) · `CardInteractive` (behaviour) · `CardSurface` (`[data-surface]` + roving focus) · `CardPreview` · `CardContextMenu` · `CardSheet` (+ `CardSheetBody`) · `cardActions.ts` (`buildCardActions`) · `CardActionsContext` (page-level store deps) |
| Menu | `components/menu/Menu`, `MenuItem`, `MenuGroup`, `Submenu` (portaled) |
| Popover | `components/popover/Popover` (portal + fixed + fade) |
| Reason | `components/reason/ReasonLine`, `SourceBadge`, `reasonText.ts` |
| Workbench | `components/workbench/DeckHeader`, `CountPill`, `RoleLedger`, `BracketVital`, `DoctorRail`, `RailTabs`, `rail/{RailRow,SuggestTab,CutsTab,TuneUpTab,CombosTab,PivotTab}` |
| Feedback | `components/feedback/Toast`, `ToastHost`, `toastStore.ts` |
| State | `store/preview.ts`, `store/cuts.ts`, `store/ui.ts` (+ railTab/railStack/menu/sheet/railSheetOpen/mobileFindOpen), `store/deck.ts` (+ undo ring: `history`/`future`/`undo`/`redo`, not persisted) |

## Old → new

| Old | Replaced by | Notes |
|---|---|---|
| `HoverPreview.tsx` (per-card, cursor-following) | `CardPreview` singleton + `useHoverIntent` | **Done** (`npx tsc --noEmit` clean 2026-11-06). `<CardPreview/>` is mounted in `page.tsx`; `HoverPreview.tsx` is deleted (`git status` `D`); `CardTile` uses `CardInteractive`; `IerTooltip` only mentions it in a comment. `useUI.cardMenuOpen` no longer exists (verified by grep 2026-11-06). |
| `CardHoverDetail.tsx` (unused) | — | **Deleted** (`git status`: `D`). |
| `CardMenu.tsx` | `CardContextMenu` + `buildCardActions` | **Done.** `CardMenu.tsx` deleted; `page.tsx` wraps the app in `<CardActionsProvider deps={actionDeps}>` and mounts `<CardContextMenu/>`. |
| `CardTile.tsx` | `CardInteractive size="tile" context="find"` + a `.dd-actions` child for the action bar | **Landed (typecheck clean 2026-11-06; browser behaviour not re-verified).** `CardTile.tsx` now wraps `CardInteractive` and `usePreview`; `IerTooltip` kept with its own cursor tracker (not yet on `Popover` + `computePlacement`). |
| `BoardCard.tsx` | `CardInteractive size="pile" context="deck"` with `dragHandle={{...listeners, ...attributes}}` | **Done** (`BoardCard.tsx`, `CardPile.tsx` import from `components/card/`). Lift is 10 px (was 18). |
| `SearchPanel.CardWithMenu` | `CardSurface id="find" orientation="grid"` wrapping `CardInteractive` | **Done** (`SearchPanel.tsx` imports from `components/card/`). |
| `CommanderStrip.tsx` cards | `CardInteractive context="commander"` inside a `CardSurface orientation="row"` | **Done** (`CommanderStrip.tsx` imports from `components/card/`). |
| `SuggestionsPanel.ReasonChips` | `ReasonLine` | **Partly done:** `SuggestionsPanel`, `DeckDoctorPanel`, `workbench/rail/RailRow` use `ReasonLine`; `ReasonChips` still used by `CardUpgradePanel`, `UpgradeSweepPanel` and `workbench/rail/TuneUpTab` (and still exported from `SuggestionsPanel`). |
| `SuggestionsPanel`, `DeckDoctorPanel` (cuts), `UpgradeSweepPanel`, `DeckCombosPanel` | `DoctorRail` tabs (`SuggestTab`, `CutsTab`, `TuneUpTab`, `CombosTab`, `PivotTab`) | **In progress.** Tabs exist and are fed by `WorkbenchLive` (Suggest/Cuts/Combos/TuneUp); `PivotTab` is an empty state (no backend endpoint — agent T is building one). The four drawers are still mounted in `page.tsx` with their own bodies; nothing moved out of them yet. `DeckDoctorPanel`'s bespoke undo → `useUndoableDeck`: UNKNOWN (not verified). |
| `StatsSidebar.tsx` | `DeckHeader` (count pill, ledger, curve, bracket) | **Behind flag.** `page.tsx` renders `<WorkbenchLive>` (wrapping `EngineBoard`) instead of the handle + `StatsSidebar` only with the `workbench` flag. Layout fixed 2026-11-06 (agent X3, verified by `tests/live-mock.spec.ts` W1 + screenshots): `DeckHeader` is sticky at the top of the board column (2 rows, ≤ 96 px at ≥ 1024 px; ledger is one scrollable line, sparkline 22 px, flags past the 2nd collapse to "+N"), `DoctorRail` is the 400 px right column, the board's Neutral column is never clipped. The template handle is replaced by the header's Template button (`xl:` only) → `TemplatePanel`. `StatsSidebar` got `variant="sheet"` for the mobile sheet. Gauges go under a "Details" disclosure (phase 2). Bracket copy must read "≥ Bracket N". |
| `ZoneColumn.tsx`, `ImportExportDialog.tsx` | — | **Deleted** (`git status`: `D`). |
| `useUI.cardMenuOpen` | `useUI.menu` / `usePreview.suppressed` | **Removed** (grep: no `cardMenuOpen` in `frontend/src`, 2026-11-06). |

## Order to swap (each step keeps the app working)

Status verified 2026-11-06 05:56 by `git status` + grep of `frontend/src` (no typecheck, no browser run).
Agent letters are the parallel workers active at that time; "by whom" is UNKNOWN where not stated.

1. **DONE** — Mount the singletons in `page.tsx`: `<CardPreview/>`, `<CardContextMenu/>`, `<CardSheet/>`, `<ToastHost/>`
   (`app/page.tsx` lines ~591–594); page wrapped in `<CardActionsProvider deps={actionDeps}>` (~441); `useUndoHotkeys()`
   called (~193); `menuOpen`/`sheetOpen` are part of `anyOverlayOpen` fed to `useBackToClose` (~205–251).
2. **DONE for `SearchPanel`** (`CardSurface` + `CardInteractive`, `SearchPanel.tsx`). **DONE for
   `CardTile`** (imports `CardInteractive` + `usePreview`; `HoverPreview.tsx` deleted; `npx tsc --noEmit` clean 2026-11-06; browser behaviour not re-verified).
3. **DONE** — `BoardCard`/`CardPile`/`CommanderStrip` use `CardInteractive`; `HoverPreview.tsx`, `CardMenu.tsx`,
   `CardHoverDetail.tsx`, `ZoneColumn.tsx`, `ImportExportDialog.tsx` all deleted. `useUI.cardMenuOpen` is gone. (Agent P is restyling cards in `components/card/`.)
4. **IN PROGRESS** — `ReasonLine` in `SuggestionsPanel` + `DeckDoctorPanel`; `ReasonChips` remains in
   `CardUpgradePanel`, `UpgradeSweepPanel`, `workbench/rail/TuneUpTab`.
5. **IN PROGRESS (phase 2)** — `WorkbenchLive` (`DeckHeader` + `DoctorRail`) is mounted behind the `workbench` flag in
   place of `StatsSidebar`; Suggest/Cuts/Combos/TuneUp tabs fetch real data; Pivot waits on a backend endpoint
   (agent T); cut-to-100 flow in progress (agent U). **TODO:** flip the default, fold `StatsSidebar` gauges, move
   drawer bodies out of `SuggestionsPanel`/`DeckDoctorPanel`/`UpgradeSweepPanel`/`DeckCombosPanel` (all four still
   mounted in `page.tsx` ~466–479) (the unused `useUI.findCollapsed` was removed 2026-11-06 by the cleanup pass; a Find rail collapse would need a new flag).
6. **DONE (2026-11-06, agent X3; `tests/live-mock.spec.ts` live-mock-mobile + `live-mobile-*.png`)** — < 1024 px
   (`useDesktop`, `components/workbench/useDesktop.ts`; `lg` breakpoint): `page.tsx` stacks header → board → 56 px bar;
   the top header folds its actions behind `≡` and gains `⌕ Find` (`useUI.mobileFindOpen`: `SearchPanel` in a
   full-screen overlay with a Done bar, `[data-testid="find-panel"]`); with the flag the bar is
   `RailTabs variant="bar"` and the rail opens as `BottomSheet` (`components/workbench/BottomSheet.tsx`, 60 vh, grab
   handle → 90 vh, `useUI.railSheetOpen`, Back/Esc/scrim close); without the flag the bar is `Stats` (StatsSidebar
   `variant="sheet"` in a `BottomSheet`) + `Template`. `EngineBoard` engine columns wrap full-width below `lg`.
   Still TODO from §4.9: drag-to-resize the sheet, lanes/piles wrapping at 64 px cards, touch-disabled DnD.

## Open questions for the owner

- When does `WorkbenchLive` become the default (flag removed, old `StatsSidebar` + drawers deleted)? Before or after the
  two-family review/commit of the framework?
- Should `IerTooltip` be rebuilt on `Popover` now, or kept on its own cursor tracker until phase 5?
- Should `ReasonChips` be deleted outright once `TuneUpTab`/`UpgradeSweepPanel`/`CardUpgradePanel` switch, or kept
  for panels that only have an id (no card name for `reasonText`)?
- Pivot: does the `/deck/pivot` contract (agent T) return per-commander keep-% only, or also the swap list the tab
  should render?
- Commit granularity: one commit per layer (ui/, card/, menu/, popover/, feedback/, reason/, hooks/, workbench/,
  stores, backend `interactions.py`) as `STATUS-2026-11-06.md` proposes, or one squash for the branch?

## Decisions taken while building (differ from or refine the plan)

- **No `@floating-ui/react-dom`.** The preview keys its main axis off the *surface* rect and its cross
  axis off the *anchor* rect; floating-ui's middleware doesn't model two reference rects without a custom
  middleware of about the same size as `usePopoverPlacement.ts` (~190 lines, pure, gallery-covered).
- Submenus are **portaled** (the parent menu scrolls; an overflow container clipped them).
- A **cut candidate** shows ✂ in the top-right corner and hides the IER pill there (two-corner rule).
- `reasonSentence` for `cooccurrence` omits the "(lift x)" suffix: the backend's `value` for that signal
  is a normalised score, not a lift, so it is shown on the chip as a bare number instead of mislabeled.
- The lead reason is the highest `value`, except `staple` only leads when it is the only signal.
- Card surfaces use `role="group"` and cards `role="button" aria-haspopup="menu"` (plan said grid/list);
  the roving-tabindex behaviour is the same and the role is honest for a screen reader.
- `CardSheet` shows the image beside the text (max 140 px wide) instead of full-width so the action rows
  fit in 70 vh; revisit in phase 5.
- Fixtures: 16 real cards (plan said 8) so the find grid of 12 has no repeats; `mechanic_tags` on them are
  fixture annotations (they come from the scoring DB in the real app).

## Grok build log (2026-11-06) — F-01 Cuts, F-02 Pivot

Cuts tab calls `POST /deck/cuts?to_100=true&target=N` (`frontend/src/lib/cuts.ts`). The header shows the response `over_by`, a 1–30 target, and "Cut all" for rows that do not break quota. Each row uses the backend `reason` sentence. `breaks_quota` rows get a red rail, "Below quota", and "Cut anyway", and they are left out of Cut all. Cut all is one undo step; a per-row cut uses the existing undo toast. A shortfall banner appears only when `shortfall` is set.

Pivot tab calls `POST /deck/pivot` through `findCommanderPivots`. It shows the current commander's score as the baseline, ranked candidates with the `reason` sentence and coverage / inclusion / synergy / off-colour chips, and an Include all toggle (`include_all=true`). An empty candidate list says no candidate beats the current commander. List only names the off-colour cards. It does not change the commander.

`npx tsc --noEmit` in `frontend/` was clean before the last CSS-only thumb fix. `npx playwright test tests/live-mock.spec.ts` after that fix: 20 passed, 8 skipped, 0 failed (28 total; the skips are the existing mobile pointer/keyboard tests). Desktop 1440×900 and mobile 390×844 screenshots of both tabs were reviewed. Row thumbs had been stretching to the row height (Meren's art ran through the off-colour list); `items-start` on the row keeps the 40px thumb at the top. Nothing committed.
