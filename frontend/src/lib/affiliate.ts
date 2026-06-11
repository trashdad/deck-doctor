/**
 * Affiliate / partner URL helpers for external deck-site handoffs.
 *
 * Sub-feature C will add the actual affiliate ref/partner query params once
 * the partnership details are confirmed.  This module already reads the env
 * var so sub-feature C only needs to set the env var and add the param to
 * the URL below — no callers need to change.
 */

// TODO (sub-feature C): set NEXT_PUBLIC_MANAPOOL_REF in .env.production to
// the agreed affiliate ref value once the ManaPool partnership is finalised.
const _MANAPOOL_REF = process.env.NEXT_PUBLIC_MANAPOOL_REF ?? "";

/**
 * Returns the ManaPool "add deck" page URL.
 *
 * When NEXT_PUBLIC_MANAPOOL_REF is set, the affiliate ref param will be
 * appended automatically (sub-feature C).
 *
 * @example
 *   // Without ref (default):
 *   manapoolAddDeckUrl()  // → "https://manapool.com/add-deck"
 *
 *   // With ref (after sub-feature C):
 *   NEXT_PUBLIC_MANAPOOL_REF="simmander"
 *   manapoolAddDeckUrl()  // → "https://manapool.com/add-deck?ref=simmander"
 */
export function manapoolAddDeckUrl(): string {
  const base = "https://manapool.com/add-deck";
  if (!_MANAPOOL_REF) return base;
  // TODO (sub-feature C): confirm the exact param name ManaPool uses
  // (candidates: ?ref=, ?partner=, ?utm_source=).
  return `${base}?ref=${encodeURIComponent(_MANAPOOL_REF)}`;
}
