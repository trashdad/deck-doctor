# Affiliate Links (ManaPool + TCGplayer) — Design Spec

**Date:** 2026-06-11 · **Status:** approved (build-it-all directive), ready to plan
**Sub-feature C.** Every card gets buy links to ManaPool and TCGplayer carrying our affiliate codes;
the ManaPool deck-cart handoff (from B) also carries the ref. Config-driven — works without codes
(links go to bare product pages); affiliate params appear once codes are set.

## Goal
Surface a "Buy" affordance on every card (ManaPool + TCGplayer), with affiliate attribution when
configured. Reuse for B's ManaPool "add all to cart".

## Affiliate link formats (from research — see program memory)
- **ManaPool card:** `https://manapool.com/card/<name-slug>?ref=<REF>` (slug = name lowercased, spaces→`-`,
  strip apostrophes/commas; for `A // B` use the FRONT face). Without a ref, omit the `?ref=`.
- **ManaPool add-deck (cart):** `https://manapool.com/add-deck?partner=<PARTNER>&ref=<REF>` (both optional).
- **TCGplayer card:** affiliate is via Impact, wrapping a destination URL:
  `https://tcgplayer.pxf.io/c/<ACCOUNT>/<CAMPAIGN>/<AD>?u=<url-encoded destination>` where destination =
  `https://www.tcgplayer.com/search/all/product?q=<name>` (search-by-name, since we don't have TCG product
  ids). If the Impact path isn't configured, link directly to the bare `…/search/all/product?q=<name>`.

## Config (frontend env — links are built client-side; `NEXT_PUBLIC_*` so they reach the browser)
- `NEXT_PUBLIC_MANAPOOL_REF` — ManaPool referral code (TapFiliate).
- `NEXT_PUBLIC_MANAPOOL_PARTNER` — optional partner tag for `/add-deck` (default: omit).
- `NEXT_PUBLIC_TCGPLAYER_IMPACT` — the Impact path segment `<ACCOUNT>/<CAMPAIGN>/<AD>` (e.g. `1234567/56789/0`),
  used to build `tcgplayer.pxf.io/c/<that>`. If empty → bare TCGplayer search links (no affiliate).
- Add a `frontend/.env.local.example` documenting these + a README note. The user supplies real values
  later; nothing breaks if unset.

## Implementation
- **`frontend/src/lib/affiliate.ts`** (extend the stub B created):
  - `manapoolSlug(name)`, `manapoolCardUrl(name) -> string`, `manapoolAddDeckUrl() -> string` (add
    `?partner`/`?ref` when set — B already calls this; enhance it).
  - `tcgplayerCardUrl(name) -> string` (Impact-wrapped when configured, else bare search).
  - All pure, env-driven, SSR-safe (guard `process.env`). Unit-style sanity is fine to skip (no test runner);
    keep the functions tiny + obviously correct.
- **Where the links appear — `frontend/src/components/CardMenu.tsx`** (the existing click menu on cards):
  add a **"Buy"** row with two links — `ManaPool ↗` and `TCGplayer ↗` — `target="_blank" rel="noopener
  noreferrer"`, built from the card name. This menu already opens on card click across the app (search,
  board), so "every card" is covered in one place. Also add the two links to **`CardHoverDetail.tsx`** if it
  has a footer area (optional, secondary).
- Keep the amber/jewel styling; small `↗` external-link affordance.

## Out of scope
- No price fetching/display (just links). No per-printing product ids (search-by-name is the fallback).
- No backend changes — purely frontend link construction.
- The user must supply real affiliate codes via env to earn commissions; the feature ships functional
  (bare product links) without them.
