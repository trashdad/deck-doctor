import type { Card } from "./types";
import { matchingZones } from "./functions";

// The designated category "zones" of the builder board.
export const ZONES = [
  "Commanders",
  "Lands",
  "Ramp",
  "Card Draw",
  "Removal",
  "Board Wipes",
  "Counters",
  "Tokens",
  "Utility",
] as const;

export type Zone = (typeof ZONES)[number];

// Auto-categorize a freshly added card using its machine-coded mechanic tags
// (from the simmander DB via the scoring store) and type line. This is what
// makes adding a card "just land" in the right lane.
//
// Delegates to matchingZones (lib/functions.ts) so both autoZone and the Engine
// Board use the same priority list and can never drift.
export function autoZone(card: Card): Zone {
  if (card.type_line.includes("Legendary Creature")) return "Commanders";
  return matchingZones(card)[0];
}

export const MANA_COLORS: Record<string, string> = {
  W: "#f8f5e3",
  U: "#3b82f6",
  B: "#5b4a63",
  R: "#ef4444",
  G: "#22c55e",
  C: "#9aa0a6",
};
