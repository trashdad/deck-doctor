/**
 * Affiliate / partner URL helpers for external card + deck handoffs.
 *
 * These are PUBLIC affiliate identifiers (they appear in every outbound link),
 * so the real codes are the built-in defaults — links carry attribution on every
 * build with no env setup. Each can still be overridden via a NEXT_PUBLIC_* env
 * var (set in .env.local — see .env.local.example). All functions are SSR-safe.
 *
 *   NEXT_PUBLIC_MANAPOOL_REF        ManaPool referral code            (default: simmander)
 *   NEXT_PUBLIC_MANAPOOL_PARTNER    ManaPool /add-deck partner tag    (default: simmander)
 *   NEXT_PUBLIC_TCGPLAYER_IMPACT    TCGplayer Impact base URL         (default: partner.tcgplayer.com link)
 *   NEXT_PUBLIC_AMAZON_TAG          Amazon Associates tag             (default: simmander-20)
 */

const MANAPOOL_REF = process.env.NEXT_PUBLIC_MANAPOOL_REF ?? "simmander";
const MANAPOOL_PARTNER = process.env.NEXT_PUBLIC_MANAPOOL_PARTNER ?? "simmander";
// Full Impact base (account/campaign/ad already in the path); we append ?u=<dest>.
const TCGPLAYER_IMPACT =
  process.env.NEXT_PUBLIC_TCGPLAYER_IMPACT ??
  "https://partner.tcgplayer.com/c/7268691/1780961/21018";
const AMAZON_TAG = process.env.NEXT_PUBLIC_AMAZON_TAG ?? "simmander-20";

// ---------------------------------------------------------------------------
// ManaPool
// ---------------------------------------------------------------------------

/**
 * Card name → ManaPool URL slug: front face of `A // B`, lowercased, punctuation
 * stripped, spaces → hyphens.
 * @example manapoolSlug("Krenko, Mob Boss") // "krenko-mob-boss"
 *          manapoolSlug("Fire // Ice")      // "fire"
 */
export function manapoolSlug(name: string): string {
  const front = name.split("//")[0].trim();
  return front
    .toLowerCase()
    .replace(/[^a-z0-9 ]/g, "")
    .trim()
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}

/** ManaPool card page with the `?ref=` affiliate param. */
export function manapoolCardUrl(name: string): string {
  const base = `https://manapool.com/card/${manapoolSlug(name)}`;
  return MANAPOOL_REF ? `${base}?ref=${encodeURIComponent(MANAPOOL_REF)}` : base;
}

/** ManaPool "add deck" (mass-entry cart) page with partner + ref params. */
export function manapoolAddDeckUrl(): string {
  const params: string[] = [];
  if (MANAPOOL_PARTNER) params.push(`partner=${encodeURIComponent(MANAPOOL_PARTNER)}`);
  if (MANAPOOL_REF) params.push(`ref=${encodeURIComponent(MANAPOOL_REF)}`);
  const base = "https://manapool.com/add-deck";
  return params.length ? `${base}?${params.join("&")}` : base;
}

// ---------------------------------------------------------------------------
// TCGplayer (via Impact)
// ---------------------------------------------------------------------------

/**
 * TCGplayer search-by-name, wrapped in the Impact affiliate link when configured.
 * @example tcgplayerCardUrl("Sol Ring")
 *   // "https://partner.tcgplayer.com/c/7268691/1780961/21018?u=https%3A%2F%2Fwww.tcgplayer.com%2Fsearch%2Fall%2Fproduct%3Fq%3DSol%2520Ring"
 */
export function tcgplayerCardUrl(name: string): string {
  const destination = `https://www.tcgplayer.com/search/all/product?q=${encodeURIComponent(name)}`;
  if (!TCGPLAYER_IMPACT) return destination;
  return `${TCGPLAYER_IMPACT}?u=${encodeURIComponent(destination)}`;
}

// ---------------------------------------------------------------------------
// Amazon (Associates)
// ---------------------------------------------------------------------------

/** Amazon search for the card (MTG-scoped) with the Associates `tag`. */
export function amazonCardUrl(name: string): string {
  const q = encodeURIComponent(`${name} Magic The Gathering`);
  const base = `https://www.amazon.com/s?k=${q}`;
  return AMAZON_TAG ? `${base}&tag=${encodeURIComponent(AMAZON_TAG)}` : base;
}
