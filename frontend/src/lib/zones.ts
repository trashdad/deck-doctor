import type { Card } from "./types";

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
export function autoZone(card: Card): Zone {
  const t = (card.type_line || "").toLowerCase();
  const tags = card.mechanic_tags || [];
  if (card.type_line.includes("Legendary Creature")) return "Commanders";
  if (t.includes("land")) return "Lands";
  if (tags.includes("board_wipe")) return "Board Wipes";
  if (tags.includes("removal")) return "Removal";
  if (tags.includes("ramp")) return "Ramp";
  if (tags.includes("card_draw")) return "Card Draw";
  if (tags.some((x) => x.startsWith("counter_"))) return "Counters";
  if (tags.some((x) => x.startsWith("token_"))) return "Tokens";
  return "Utility";
}

export const MANA_COLORS: Record<string, string> = {
  W: "#f8f5e3",
  U: "#3b82f6",
  B: "#5b4a63",
  R: "#ef4444",
  G: "#22c55e",
  C: "#9aa0a6",
};
