# Real-backend tests for the Suggest / Combos / Tune-up tabs and the mobile sheet (2026-11-24)

**New file:** `tests/live-real-tabs.spec.ts`. **Changed file:** `playwright.config.ts` (new projects
`live-real-tabs-desktop` at 1440x900, and `live-real-tabs-mobile` with iPhone 13 geometry on Chromium).
The tests use no `page.route` mocks. The deck is built through the real API in `beforeAll`, in the same
way as `live-real.spec.ts`: Wayta plus `/deck/complete` plus 6 extra picks, 106 cards. Each test
captures the response the page itself received (`page.waitForResponse`) and compares the page
against it.

## Tests

| # | Project | Test | What it proves |
|---|---|---|---|
| 1 | desktop | Suggest rows carry the backend's reasons; `+` adds exactly one; Undo restores | The row ids and their order equal `/deck/recommend` minus the staple-only cards and the cards already in the deck. The Source line matches the response's `tier`. On the first 8 rows, every chip tooltip is one of that card's backend `detail` strings, and "why" lists every `detail` word for word. `+` adds exactly 1 card (localStorage and the count pill) and the row disappears. Clicking the exact `Undo` button should restore the deck. |
| 2 | desktop | Suggest respects color identity | No suggestion falls outside Wayta's identity (GRW). The widest-identity row (2 or more colours) is added and lands in the deck, and no card in the deck falls outside the identity. |
| 3 | desktop | Combos tab lists the real Spellbook combos | The request body holds exactly the seeded deck. The header counts and the footer match `complete` and `near`. Every member of a complete combo is in the deck. The first 10 combo boxes show the response's `produces` and its members in order. Every near combo's missing card is not in the deck and is in identity, and "add X" names it. `+ Add` adds 1 card, and the refetched `/deck/combos` then lists that combo as complete. |
| 4 | desktop | Tune-up renders the real upgrade-sweep | `weak=16` and the commander are sent. The number of rows equals the number of swaps. Each swap shows the target name, the backend's weakness `detail`s as the first two chips, and the options in backend order. Swap keeps the count, removes the target and puts the replacement in the target's lane. Missing controls are recorded as annotations. |
| 5 | mobile | The tab bar opens the sheet, tabs switch, tapping the same tab closes it | There is no desktop rail. The bar sits at the bottom of the viewport and every tab is at least 44 px tall. Cuts opens the sheet with the real `to_100` overage and row count. Pivot then replaces Cuts in the same sheet. Suggest rows match `/deck/recommend`. Tapping Suggest again closes the sheet. `scrollWidth <= innerWidth` holds at every step. |
| 6 | mobile | Cuts in the sheet: Cut all reachable, 44 px targets | Cut all is fully in the viewport and inside the sheet. Touch targets of at least 44 px are checked with soft asserts. Cut all brings the deck to 100 and the toast Undo (in view) restores 106. There is no horizontal overflow. |
| 7 | mobile | Suggest in the sheet | The rows match the response, the chip tooltips are backend details, `+` is at least 44x44, `+` adds exactly 1 card and its row disappears, and there is no overflow. |

Each test skips itself in the other project, so 14 entries run as 7 tests plus 7 skips.

## App bugs found (not fixed — app source is owned elsewhere)

1. **Adding from Suggest or Combos, or using Swap in Tune-up, gives no Undo toast.**
   `frontend/src/components/workbench/WorkbenchLive.tsx:257` passes `onAdd={add}`, and `add` is the
   raw store action from `:53` (`useDeck((s) => s.add)`), not `undoable.add` (`:55`).
   `DoctorRail` passes this `onAdd` to both SuggestTab and CombosTab. Likewise, `:255` passes
   `onSwap: swap`, the raw store action from `:54`. History is still pushed, so Ctrl+Z works, but no
   "Added X · Undo" toast appears, unlike Cuts and the card menu (page.tsx:323).
   **Repro:** open `/deck-doctor?workbench=1` with a commander set and click `+` on any Suggest row.
   The count goes up by 1 and no toast appears. Test 1 fails at `live-real-tabs.spec.ts:145`, the
   `Undo` click, every time. The mocked test hides this: `tests/live-mock.spec.ts:474`
   (`if (hasToast)`) passes when there is no toast.
2. **The mobile touch targets are under 44 px** (measured at iPhone 13 geometry):
   - Cut all is 32 px tall (`frontend/src/components/workbench/rail/CutsTab.tsx:108`, `h-8`). The
     `cuts-target` input at `:90` is `h-8` too.
   - The toast Undo button is 36 px tall (`frontend/src/components/feedback/Toast.tsx:22`, `h-9`).

   The row Cut and `+` buttons and the tab-bar tabs pass, at 44 px or more. Test 6 reports these as
   soft failures; the cut-all-then-undo flow itself passes.
3. **Backend: concurrent deck requests open a new Postgres session for every query.**
   `backend/app/db.py:27` builds the `ThreadedConnectionPool` with `minconn=1`. psycopg2's
   `putconn` closes any returned connection once the idle pool already holds `minconn`, so whenever
   more than one request runs at a time, each query beyond the first reconnects. Measured directly
   against :8001 with the seeded deck:

   | `/deck/recommend` calls at once | Time | New Postgres sessions (`pg_stat_database.sessions`) |
   |---|---|---|
   | 1 | 169 ms | 0 |
   | 2 | 249 ms | 1 |
   | 4 | 35.7 s | 881 |

   `/deck/analyze` and `/deck/cuts` behave the same (4 at once: 9 s and 30 s). `/health`,
   `/cards/commanders` and `/deck/combos` stay fast. A single page load already fires
   analyze, recommend and cuts together, so next dev's `/api` proxy gives up with `socket hang up`
   and the browser gets 500s. This is the main reason the real-backend tests fail in parallel runs,
   and why beforeAll's `/deck/complete` timed out at 90 s. Impact on prod (Linux, where connecting
   is cheaper) is UNKNOWN. Possible fix (not applied): keep connections alive, for example by setting
   `minconn` to the expected concurrency, or move to `psycopg_pool`.

## Tune-up: controls the rail tab lacks (compared with UpgradeSweepPanel)

- No efficiency slider (`sweep-slider`) and no "Favor commander synergy" toggle. The tab silently
  reuses the drawer's `useSweepStore` values; the observed request was `efficiency=0.4&favor_synergy=true&weak=16`.
- The empty-state text says "**Run Tune-up** to start" (`TuneUpTab.tsx:33`), but there is no such
  button. The query fires automatically when the tab opens.
- There is no Undo toast after Swap (bug 1).

## Color identity: what can and cannot be tested from the UI

`/deck/recommend`, the `near` list of `/deck/combos` and `/cards?commander_id=` all filter by identity
on the server, so the real data never offers an off-colour card to add. The client gate
(`frontend/src/store/deck.ts`, the `withinIdentity` check in `add`) therefore cannot be reached from
these tabs. Test 2 checks the server-side filter and that a legal multicolour card is accepted.

## Mutation checks (each source file backed up, mutated, the test run, then restored and checked with sha256 — all `OK`)

| Mutation | Test | Failed at |
|---|---|---|
| `TuneUpTab.tsx`: options rendered in reverse | 4 Tune-up | spec:266, options order (`toEqual`) |
| `CombosTab.tsx`: `complete.slice(1).map` | 3 Combos | spec:203, expected 76 combo boxes, got 75 |
| `SuggestTab.tsx`: `reasons={s.reasons.slice(0, 1)}` | 1 Suggest | spec:132, expected 3 evidence rows, got 1 (before the Undo step) |
| `WorkbenchLive.tsx`: same-tab-closes branch disabled | 5 mobile tabs | spec:351, the sheet is still open |

After the checks, `git status` shows no change to SuggestTab, CombosTab, TuneUpTab or
WorkbenchLive. `CutsTab.tsx` shows as modified because another agent is editing it.

## Suite runs (`npx playwright test --reporter=line`)

The whole suite has 125 entries across all projects.

| Run | Passed | Failed | Skipped | Did not run | Failures |
|---|---|---|---|---|---|
| Default workers | 71 | 4 | 36 | 14 | `engine3` (no cards placed), `live-real` Cuts beforeAll (30 s), and `live-real-tabs` beforeAll on both projects (90 s). All are backend overload from bug 3; the 14 that did not run are tests blocked behind those beforeAll hooks. |
| `--workers=1` | 78 | 4 | 43 | 0 | All 4 are new tests: test 1 (bug 1, always fails at :145); test 6 (bug 2, soft size asserts; the flow passes); test 4 Tune-up and test 7 mobile Suggest (no `/deck/upgrade-sweep` or `/deck/recommend` response within 60 s, because the proxy logged `socket hang up` on analyze, cuts, recommend and upgrade-sweep — bug 3). |

`engine3` and `live-real.spec.ts` pass with `--workers=1`. The earlier isolated `--workers=1` run of
only the two new projects passed tests 2, 4, 5 and 7. Test 3 asserted its data and its `+ Add`
completion correctly, but failed on console 500s from analyze and cuts hang-ups during that run.
So tests 2, 3, 4, 5 and 7 are correct against the real backend. They fail only when bug 3 makes the
backend drop requests, which happens even at one worker, because a single page load fires 3 deck
requests at once. Tests 1 and 6 fail on real UI bugs (1 and 2).

## Environment notes

- Other agents were editing the tree while these runs happened (`next.config.mjs`, the ui-kit page
  moved to `page.dev.tsx`, `CutsTab.tsx`, and backend `cut_to_100.py`, `doctor.py`, `suggest.py`).
  One early run was lost when a half-written `next.config.mjs` crashed next dev with
  `nextConfig is not defined`.
- `tools/eval/backtest_cuts.py` and gate pytest runs were using the CPU at the same time.
