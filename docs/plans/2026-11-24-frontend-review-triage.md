# Frontend review triage — 2026-11-24

Input: the cross-family static review of the workbench (`review_ds.md`, findings F-01..F-25, made
without running anything), plus two items the coordinator added from the real-backend tests (A, B).
Method: each finding was reproduced first, as a Playwright test in `tests/live-mock.spec.ts` (mocked
backend, describe block "Review triage 2026-11-24") or by reading the exact code lines when the
issue is purely static. The test was run and seen to fail before the fix, and passes after it.
Final run: `npx tsc --noEmit` clean; `npx playwright test tests/ui-kit.spec.ts tests/live-mock.spec.ts`
gives 94 passed, 55 skipped. The skips are by design: projects that don't apply, such as desktop-only
tests in the mobile project.

| Finding | Reproduced | Fixed | Test (tests/live-mock.spec.ts unless noted) / note |
|---|---|---|---|
| F-01 load pollutes undo ring | yes (Ctrl+Z after load → 36 cards, not 103) | yes: `decks.load` uses one `loadImported` write | F-01 loading a saved deck is ONE undo step |
| F-02 basics multiplicity / remove / add | yes (lane "1", Remove no-op, 2nd Mountain pile) | yes: pile ×N + lane count sums quantity; `store.remove` drops one basic copy; `store.add` bumps basics | F-02a, F-02b, F-02c |
| F-03 Move → Commanders bypasses validation | yes (submenu listed Commanders) | yes: submenu omits it; `store.move` refuses moves into/out of Commanders | M2 (live-mock) and M4 (ui-kit), both updated |
| F-04 commander/partner can be cut | yes (frontend showed a Commanders-zone cut row) | yes (frontend only): rows in the Commanders zone are filtered out; `cutOne`/`cutAll` skip them. The backend still excludes only the first `commander_id`, so it could return a partner. That backend change is not in my scope. | F-04 |
| F-05 zone-only moves not autosaved | yes (it passed at first only because the test moved inside the post-load save window; the tightened test failed) | yes: autosave signature includes zone | F-05 |
| F-06 / A raw add/swap/remove: no Undo toast | yes (Suggest +, board Delete: no toast) | yes: rail add/swap, Find add, drag move and board remove all go through `useUndoableDeck` | F-06, W2 (now unconditional) |
| F-07 toast Undo undoes the wrong action | yes (stale toast removed an unrelated add) | yes: `undoLatestAction()` binds each toast to its own history snapshot; a stale toast does nothing | F-07 |
| F-08 sticky target / Cut all undershoot | yes, both (target stuck at 3 at 105 cards; "Cut all 5" with no over_by) | yes: a manual target holds only while the deck size is unchanged; the Cut-all batch is capped at min(target, local count−100, over_by) | F-08a, F-08b (W8 still passes) |
| F-09 errors shown as empty states | yes (Suggest showed "Nothing left to suggest") | yes: error states for Suggest, Combos and the bracket vital | F-09 |
| F-10 pending hover timer → ghost preview | yes (preview anchored to the removed row) | yes: a pending open is cleared on unmount; `showNow` ignores detached nodes | F-10 |
| F-11 rail list torn down, focus lost | yes (focus fell to body after keyboard Cut) | yes: `keepPreviousData` on Suggest, and on Cuts while the deck is over 100; Cuts re-focuses the next row's Cut button | F-11 |
| F-12 sheets lack modal focus; 90vh off-screen | yes (focus stayed outside; top < 0 at 390×360) | yes: `useDialogFocus` (focus in, Tab trap, restore) on BottomSheet and CardSheet; height capped at `100vh − offset` | F-12 |
| F-13 railSheetOpen survives the desktop breakpoint | yes (sheet re-opened after resizing back) | yes: crossing to desktop closes it | F-13 |
| F-14 tabs lack the keyboard model | yes (every tab was a Tab stop; no arrow keys) | yes: roving tabindex, ←/→/Home/End, `aria-controls`, a `role=tabpanel` body | F-14 |
| F-15 focus lost on Delete | yes (body) | partly: Delete moves focus to the card now in that position. Not done: the nested `<button>` inside `role=button`, and focus after menu → Remove. Both are structural. | F-15 |
| F-16 cut-candidate flag never rendered | yes (no `data-cut`) | yes: BoardCard passes `cutCandidate`. These flags are set in the frontend; they don't come from the backend, so the skip condition didn't apply. | F-16 |
| F-17 hydration mismatch | **no**. The server HTML says "0 cards", but zustand 4.5's `useStore` hydrates from `getInitialState` (the server snapshot) and then re-renders, so React reports no mismatch. No hydration error in either project. | n/a | F-17 (guard: fails on any hydration error) |
| F-18 scrolling a submenu closes the menu | static: `CardContextMenu.onScroll` only excluded `menuRef`, not the portaled `.dd-submenu` | yes: uses the existing `inside()` helper | no browser test (9-item submenu doesn't scroll at test viewports) |
| F-19 dead Combos/Tune-up buttons | yes (chip click did nothing) | yes: `onOpenCard` → relationship explorer ("similar") | F-19 |
| F-20 setCommander toast over-reports prunes | static arithmetic (`before + 1 − after` = 2 when promoting an in-deck legend) | yes: counts the cards and basic copies that actually left | F-20 (regression; written after the fix) |
| F-21 pivot selection leaks across commanders | static (`selectedId` is never reset) | yes: PivotTab is keyed by commander id | none |
| F-22 1–5 dead on mobile with the sheet closed | yes | yes: on mobile, WorkbenchLive's listener opens the sheet on that tab | F-22 |
| F-23 broken-image state leaks across previews | static (CardPreview's `CardFrame` had no key) | yes: `key={card.id}` | none |
| F-24 per-card scroll listeners; toast timers | partly. The listeners are a perf note, not a bug, and are unchanged. Toast timers did outlive dismiss. | toast timers cleared on dismiss | none |
| F-25 latent query keys | not a bug. The combos-key-omits-zone case needed a zone-only move into Commanders, which is now impossible (F-03). | n/a | none |
| B touch targets < 44 px (Cut all, target input, toast Undo/×) | static (h-8 / h-9) | yes: `[@media(pointer:coarse)]:h-11` | B touch targets … ≥ 44 px (written after the fix) |
| B Tune-up copy names a "Run Tune-up" button that doesn't exist | static (TuneUpTab) | yes: wording changed | none (that state is only shown when the query isn't running) |

Real-backend check (`tests/live-real-tabs.spec.ts`, :8001): 5 passed, 2 failed, 7 skipped. Those 5
include the mobile Cuts sheet at 44 px, Suggest + with Undo, and Combos. On a retry, "Suggest respects
color identity" passed. "Tune-up … Swap" still fails because the Next proxy logs `socket hang up` and
the backend returns 500 on `/deck/upgrade-sweep` (also on `/deck/cuts` and `/deck/recommend`). The
frontend never gets an answer, so the Swap toast (item A) is unverified against the real backend. It
is checked on the mocked path (F-06).

Not changed: anything in `backend/**`. The backend gap in F-04 (only one `commander_id` excluded from
cuts) is a follow-up for the backend owner.
