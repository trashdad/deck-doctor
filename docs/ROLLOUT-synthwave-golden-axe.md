# Deck Doctor — "Arcade Diagnosis" theme rollout (Synthwave × Golden Axe)

Approved design: `design-previews/option-7` (full synthwave on the house `theme-synth`
palette + Golden Axe warmth, chunky gold-bevel arcade wordmark, one big floating
16-bit golden axe behind the hero, and the **Deck Doctor Diagnosis 87/100** gauge as
the hero element).

Goal: migrate the production Next.js app from the current "Arabian nights" dark-amber
theme to Arcade Diagnosis **without ever breaking the live site**, staged so each phase
is independently shippable and visually coherent on its own.

Guiding rule: re-skin by **token first**, clean up per-component second. Deploy after
each phase; if a phase looks wrong in prod, it reverts on its own (one commit).

---

## Palette (locked, from jupiter `theme-synth`)
```
violet base   #0a0420 → #1a0b3e → #2b0f54   (page bg, fixed)
magenta       #ff2bd6      cyan        #00eeff
gold          #ffd24a      amber glow  #ffae00      hot pink #ff7ad9
text          #c8b6ff / #9fd0ff / #b3a4e6          dark-on-neon #1a0033
golden-axe warmth   bronze #a8690f · sunset #e07b39 · deep gold #b8771a · hi #fff6c2
```
Fonts: **Press Start 2P** (wordmark + small arcade labels, sparingly) · **Rajdhani /
Chakra Petch** (UI/body). Replaces Cinzel.

---

## Phase 0 — Asset + token foundation (no visible change yet, low risk)
- Add `frontend/public/golden-axe.svg` (the generated 16-bit double-bit axe sprite).
- `tailwind.config.ts`: replace the palette under `theme.extend.colors` — keep the
  semantic token NAMES (`ink`, `panel`, `panel2`, `edge`, `accent`, `accent2`) so every
  `bg-panel` / `border-accent` / `text-accent` in existing components re-skins for free.
  Remap: `ink`→violet base, `panel/panel2`→translucent violet panels, `edge`→neon-dim
  border, `accent`→gold `#ffd24a`, `accent2`→magenta `#ff2bd6`. Add new tokens:
  `cyan #00eeff`, `magenta`, `sun`, `bronze`, plus `boxShadow.neon`.
- Load the fonts (next/font or `<link>`); point `--font-display` at Press Start 2P and
  set a body font var for Rajdhani.
- **Checkpoint:** build; the app should still render, now tinted toward the new palette
  via tokens alone. Deploy. (If anything's egregious, this is the revert point.)

## Phase 1 — Global chrome: background scene + wordmark (the "wow")
Files: `src/app/globals.css`, `src/app/layout.tsx`, the top-bar/header component.
- Replace `body` background with the fixed violet gradient + a CRT-scanline overlay.
- Add the hero scene as a reusable backdrop: the pink→gold **sun**, the magenta/cyan
  **perspective grid horizon**, and the **one big slowly-rotating golden axe** centered
  behind the hero (`golden-axe.svg`, `image-rendering:pixelated`, `axespin 60s` +
  `axebob`). Lift the exact CSS from option-7.
- Build the gold-bevel arcade wordmark treatment as a small component/utility class
  (stacked text-shadows) and apply to "DECK DOCTOR".
- Restyle `.mtg-card` hover glow from amber to neon.
- **Checkpoint:** landing/top fold now reads as Arcade Diagnosis. Deploy.

## Phase 2 — The Engine Board surfaces
Files: `EngineBoard.tsx`, `EngineColumn.tsx`, `CommanderStrip.tsx`, `ZoneColumn.tsx`,
`FieldSection.tsx`, `WinconHelperPanel.tsx`, `EngineStaplesPanel.tsx`, `CardTile.tsx`,
`BoardCard.tsx`.
- Sweep each for hardcoded `zinc-*`/amber utilities and inline `style={{…}}` hexes left
  over from the amber theme; move them onto tokens or the new neon values.
- Per-engine accent already keyed crimson/sapphire/emerald — keep, but wrap panels in
  the neon-border + glow treatment; engine headers get the small gold-bevel label and
  the tiny axe bullet/Staples motif.
- Win Conditions zone gets the gold accent + axe-mini motif.
- **Checkpoint:** the builder matches the mock. Deploy.

## Phase 3 — Rails, panels, modals, menus
Files: `SearchPanel.tsx`, `SuggestionsPanel.tsx`, `UserMenu.tsx`, `IerTooltip.tsx`,
`CardMenu.tsx`, `HoverPreview.tsx`, `ImportDialog.tsx`, `HowWeCalcModal.tsx`,
`TemplatePanel.tsx`, `DeckCombosPanel.tsx`, `RelationshipExplorer.tsx`,
`StatsSidebar.tsx`, `LoginModal.tsx`, etc.
- Token sweep + segmented CARD NAME/ORACLE TEXT control, add-buttons, pills, chips
  restyled to neon. Admin/Mythic chip to the arcade chip style.
- **Checkpoint:** no amber survivors anywhere. Deploy.

## Phase 4 — The real "Deck Doctor Diagnosis" score (the headline feature)
This is the one piece that is **net-new logic**, not a re-skin. Currently the 87/100 is
cosmetic. Make it real:
- **Backend** (`backend/app/`): new `diagnosis.py` computing a 0–100 deck score from
  vitals — Mana Curve, Ramp, Card Draw, Removal, Win Conditions — reusing the existing
  IER/`scoring` heuristics per card, aggregated over the deck. New endpoint
  `POST /deck/diagnose` returning `{score, verdict, vitals:[{label,score}]}`.
- **Frontend**: extend `Gauge.tsx` into the neon gold-bevel diagnosis gauge; wire it to
  the endpoint; vitals bars from real data; live-updates as the deck changes (debounced).
- This phase can be specced + built on its own branch in parallel with Phases 1–3 since
  it's additive. Ship the gauge with a heuristic placeholder if Phases 1–3 land first.
- **Checkpoint:** gauge reflects the actual deck. Deploy.

## Phase 5 — Polish & retire the old theme
- Remove dead amber CSS, the old `--font-display` fallback, unused gradients.
- Pass for legibility/contrast (neon on violet — verify text meets AA where it matters),
  reduced-motion media query (pause axe spin + scanlines for `prefers-reduced-motion`),
  and mobile/responsive down-checks.
- Playwright visual pass vs. option-7. Deploy final.

---

## Risk / rollback
- Each phase = one deploy = one-commit revert. Token-first ordering means Phase 0 alone
  can't break layout (only colors).
- Highest-risk file: `globals.css`/`layout.tsx` (Phase 1) — the fixed background scene.
  Keep the scene in one component so it's trivially toggled.
- Phase 4 backend is isolated behind a new endpoint; the gauge degrades to the
  placeholder score if `/deck/diagnose` errors.

## Locked decisions (2026-06-15)
1. **Pixel font (Press Start 2P): wordmark + section/zone headers only.** All other UI
   uses Rajdhani for readability.
2. **Diagnosis score: built for real in this effort (Phase 4).** New `/deck/diagnose`
   endpoint + live gauge — not a placeholder.
3. **Reduced-motion: pause** the axe spin + scanlines (Phase 5).
4. **Execution order:** start with Phase 0 + Phase 1, deploy, check in before the deeper
   component sweep (Phases 2–3). Phase 4 (scoring) can run in parallel.
