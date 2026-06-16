# Arcade Diagnosis — component style contract

The global theme (Phase 0–1) is ALREADY applied: Tailwind palette is remapped, fonts
loaded, and a fixed synthwave backdrop (sun + neon grid + rotating golden axe +
scanlines) sits behind the whole app. Body font is Rajdhani. You are refining individual
components to match the approved mockup. **Visual target:**
`C:\simmander\design-previews\option-7\index.html` (read it).

## Hard rules
- Do NOT touch the global backdrop, `globals.css` scene, `layout.tsx`, `tailwind.config.ts`,
  or `page.tsx`. Only edit the component files assigned to you.
- Do NOT run `npm run build` or `npm run dev` (a dev server is live; building corrupts
  `.next`). Do NOT use the browser/playwright (shared, will collide). Verify with
  `npx tsc --noEmit` only.
- Preserve ALL behavior, props, `data-testid`s, accessibility attributes, and logic.
  This is a restyle, not a refactor.
- Keep text legible on the violet base. Translucency is good, illegibility is not.

## Palette = Tailwind tokens (already defined — use these, not raw hex)
- `bg-ink` `#0a0420` violet base · `bg-panel` `#150d33` · `bg-panel2` `#1d1242`
- `border-edge` `#3b2a66` · `accent`/`text-accent`/`bg-accent` = gold `#ffd24a`
- `accent2` & `magenta` = `#ff2bd6` · `cyan` = `#00eeff` · `sun` `#ff7ad9` · `bronze` `#a8690f`
- Lavender body/dim text: use `text-[#c8b6ff]` / `text-[#9fd0ff]` for secondary labels.
- Shadows: `shadow-neon` (magenta+cyan glow), `shadow-glow` (gold+magenta).

## Restyle recipe
1. **Panels** become translucent so the backdrop shows: replace solid `bg-panel` with
   `bg-panel/80 backdrop-blur-sm` (modals/overlays can be `bg-ink/90 backdrop-blur-md`).
   Borders: `border border-accent/30`; for emphasis add `shadow-neon`. Engine panels keep
   their per-engine accent hue (crimson e1 / sapphire e2 / emerald e3) on the border+glow.
2. **Kill leftovers**: any `amber-*`/`yellow-*` → `accent`; `bg-white/5` hovers →
   `hover:bg-accent/10` (or `/magenta`). Greys: keep `text-zinc-200/300` for paragraphs,
   but promote titles/labels to `text-accent`, `text-cyan`, or lavender.
3. **Headers** — section / zone / panel titles get the arcade treatment:
   `className="arcade-bevel text-sm"` for prominent zone/section names (e.g. "Win
   Conditions", engine names, modal titles), or for SMALL labels use
   `font-display text-[9px] uppercase tracking-wider text-accent` (pixel but tiny).
   NEVER put `font-display`/pixel on body paragraphs, lists, or card text — Rajdhani only.
4. **Buttons**: primary/CTA → `bg-gradient-to-r from-magenta to-accent text-[#1a0033]
   font-semibold shadow-neon hover:brightness-110`; ghost/secondary → `border
   border-accent/50 text-accent hover:bg-accent/10`. Circular `＋` add buttons → neon ring
   `border border-cyan/60 text-cyan hover:bg-cyan/15 hover:shadow-neon`.
5. **Pills / chips** (IER, tags, tier badge): `border border-cyan/50 text-cyan bg-cyan/10`
   (or gold variant `border-accent/50 text-accent bg-accent/10`). Mythic badge → gold.
6. **Segmented toggles** (CARD NAME / ORACLE TEXT): active segment
   `bg-gradient-to-r from-magenta to-accent text-[#1a0033]`; inactive `text-[#9fd0ff]`.
7. **Hover glow** on interactive cards/rows: `hover:shadow-neon` or
   `hover:shadow-[0_0_18px_rgba(255,43,214,.45)]`.
8. **Golden-axe motif** (sparingly, where the mock uses it): a small pixel axe via
   `<span className="inline-block bg-contain bg-no-repeat [image-rendering:pixelated]"
   style={{backgroundImage:"url(/deck-doctor/golden-axe.svg)", width:16, height:16}} />`.
   Good spots: engine panel header bullet, the ⭐ Staples button (swap the star for the
   axe), a win-condition card corner. Don't scatter it everywhere.

## Verify
Run `npx tsc --noEmit` from `frontend/`. Report any file you changed and a one-line note
per file. If a component was already token-clean, say so rather than inventing changes.
