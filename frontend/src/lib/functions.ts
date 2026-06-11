/**
 * Card function derivation — Engine Board placement logic.
 *
 * Refactors zone matching out of autoZone so both autoZone and the engine board
 * derive from the same single function list, preventing drift.
 */
import type { Card } from "./types";
import type { Zone } from "./zones";

/**
 * Returns ALL zones that this card qualifies for, in priority order
 * (same rules as autoZone: Land > Board Wipes > Removal > Ramp > Card Draw >
 * Counters > Tokens > Utility). "Commanders" is excluded here — the board
 * handles commanders in the strip above.
 */
export function matchingZones(card: Card): Zone[] {
  const t = (card.type_line || "").toLowerCase();
  const tags = card.mechanic_tags || [];
  const matches: Zone[] = [];

  if (t.includes("land")) matches.push("Lands");
  if (tags.includes("board_wipe")) matches.push("Board Wipes");
  if (tags.includes("removal")) matches.push("Removal");
  if (tags.includes("ramp")) matches.push("Ramp");
  if (tags.includes("card_draw")) matches.push("Card Draw");
  if (tags.some((x) => x.startsWith("counter_"))) matches.push("Counters");
  if (tags.some((x) => x.startsWith("token_"))) matches.push("Tokens");

  // If none of the above matched and it's not a land, it's Utility.
  if (matches.length === 0) matches.push("Utility");

  return matches;
}

export interface CardFunctions {
  /** The primary zone — first match in the priority list (= autoZone output). */
  home: Zone;
  /** Every other matching zone this card also serves. */
  additional: Zone[];
}

/**
 * Derive the home zone and all additional zones for a non-commander card.
 *
 * home     = first match in priority order (matches autoZone).
 * additional = any other matches (multi-modal cards show ghosts here).
 *
 * Commanders are handled in CommanderStrip — pass the full card and let the
 * caller check card.type_line before calling this.
 */
export function cardFunctions(card: Card): CardFunctions {
  const all = matchingZones(card);
  const [home, ...additional] = all;
  return { home, additional };
}

export interface CardEngines {
  e1: boolean;
  e2: boolean;
}

/**
 * Determine which engine(s) a card belongs to.
 *
 * @param card       The deck card.
 * @param themeATags mechanic_tags from the theme chosen for Engine 1 (may be empty).
 * @param themeBTags mechanic_tags from the theme chosen for Engine 2 (may be empty).
 *
 * e1 = the card's mechanic_tags intersect themeATags.
 * e2 = the card's mechanic_tags intersect themeBTags.
 * Neither → neutral.
 */
export function cardEngines(card: Card, themeATags: string[], themeBTags: string[]): CardEngines {
  const tags = card.mechanic_tags || [];
  const e1 = themeATags.length > 0 && tags.some((t) => themeATags.includes(t));
  const e2 = themeBTags.length > 0 && tags.some((t) => themeBTags.includes(t));
  return { e1, e2 };
}
