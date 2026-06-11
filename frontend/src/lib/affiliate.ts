/**
 * Affiliate / partner URL helpers for external deck-site handoffs.
 *
 * All functions are SSR-safe (guard `process.env`) and work without
 * any env vars set — they return bare product URLs. Affiliate params
 * only appear when the corresponding NEXT_PUBLIC_* env var is set.
 *
 * Env vars (set in .env.local — see .env.local.example):
 *   NEXT_PUBLIC_MANAPOOL_REF       ManaPool TapFiliate referral code
 *   NEXT_PUBLIC_MANAPOOL_PARTNER   ManaPool /add-deck partner tag (optional)
 *   NEXT_PUBLIC_TCGPLAYER_IMPACT   Impact path segment ACCOUNT/CAMPAIGN/AD
 */

const _MANAPOOL_REF = process.env.NEXT_PUBLIC_MANAPOOL_REF ?? "";
const _MANAPOOL_PARTNER = process.env.NEXT_PUBLIC_MANAPOOL_PARTNER ?? "";
const _TCGPLAYER_IMPACT = process.env.NEXT_PUBLIC_TCGPLAYER_IMPACT ?? "";

// ---------------------------------------------------------------------------
// ManaPool helpers
// ---------------------------------------------------------------------------

/**
 * Converts a card name to a ManaPool URL slug.
 *
 * Rules:
 * - For double-faced / split cards ("A // B"), use only the FRONT face.
 * - Lowercase the name.
 * - Strip apostrophes, commas, colons, and other punctuation (everything that
 *   is not a letter, digit, or space).
 * - Replace spaces with hyphens.
 * - Collapse consecutive hyphens.
 * - Trim leading/trailing hyphens.
 *
 * @example
 *   manapoolSlug("Krenko, Mob Boss")  // → "krenko-mob-boss"
 *   manapoolSlug("Fire // Ice")       // → "fire"
 *   manapoolSlug("Gideon's Triumph")  // → "gideons-triumph"
 */
export function manapoolSlug(name: string): string {
  // Take only the front face for split/DFC cards
  const front = name.split("//")[0].trim();
  return front
    .toLowerCase()
    .replace(/[^a-z0-9 ]/g, "")   // strip punctuation (apostrophes, commas, colons, …)
    .trim()
    .replace(/\s+/g, "-")          // spaces → hyphens
    .replace(/-+/g, "-")           // collapse consecutive hyphens
    .replace(/^-|-$/g, "");        // trim leading/trailing hyphens
}

/**
 * Returns a ManaPool card page URL.
 *
 * When NEXT_PUBLIC_MANAPOOL_REF is set the `?ref=` param is appended.
 *
 * @example
 *   // Without ref:
 *   manapoolCardUrl("Krenko, Mob Boss")
 *   // → "https://manapool.com/card/krenko-mob-boss"
 *
 *   // With NEXT_PUBLIC_MANAPOOL_REF="simmander":
 *   manapoolCardUrl("Krenko, Mob Boss")
 *   // → "https://manapool.com/card/krenko-mob-boss?ref=simmander"
 */
export function manapoolCardUrl(name: string): string {
  const base = `https://manapool.com/card/${manapoolSlug(name)}`;
  if (!_MANAPOOL_REF) return base;
  return `${base}?ref=${encodeURIComponent(_MANAPOOL_REF)}`;
}

/**
 * Returns the ManaPool "add deck" page URL.
 *
 * When NEXT_PUBLIC_MANAPOOL_PARTNER and/or NEXT_PUBLIC_MANAPOOL_REF are set
 * the corresponding query params are appended.
 *
 * @example
 *   // Without any env vars:
 *   manapoolAddDeckUrl()  // → "https://manapool.com/add-deck"
 *
 *   // With NEXT_PUBLIC_MANAPOOL_PARTNER="simmander" and
 *   //      NEXT_PUBLIC_MANAPOOL_REF="simmander":
 *   manapoolAddDeckUrl()
 *   // → "https://manapool.com/add-deck?partner=simmander&ref=simmander"
 */
export function manapoolAddDeckUrl(): string {
  const base = "https://manapool.com/add-deck";
  const params: string[] = [];
  if (_MANAPOOL_PARTNER) params.push(`partner=${encodeURIComponent(_MANAPOOL_PARTNER)}`);
  if (_MANAPOOL_REF) params.push(`ref=${encodeURIComponent(_MANAPOOL_REF)}`);
  if (params.length === 0) return base;
  return `${base}?${params.join("&")}`;
}

// ---------------------------------------------------------------------------
// TCGplayer helpers
// ---------------------------------------------------------------------------

/**
 * Returns a TCGplayer card search URL.
 *
 * When NEXT_PUBLIC_TCGPLAYER_IMPACT is set (the Impact path segment
 * "ACCOUNT/CAMPAIGN/AD"), the destination URL is wrapped in the Impact
 * tracking link. Otherwise the bare TCGplayer search URL is returned.
 *
 * @example
 *   // Without Impact:
 *   tcgplayerCardUrl("Sol Ring")
 *   // → "https://www.tcgplayer.com/search/all/product?q=Sol%20Ring"
 *
 *   // With NEXT_PUBLIC_TCGPLAYER_IMPACT="1234567/56789/0":
 *   tcgplayerCardUrl("Sol Ring")
 *   // → "https://tcgplayer.pxf.io/c/1234567/56789/0?u=https%3A%2F%2F..."
 */
export function tcgplayerCardUrl(name: string): string {
  const destination = `https://www.tcgplayer.com/search/all/product?q=${encodeURIComponent(name)}`;
  if (!_TCGPLAYER_IMPACT) return destination;
  return `https://tcgplayer.pxf.io/c/${_TCGPLAYER_IMPACT}?u=${encodeURIComponent(destination)}`;
}
