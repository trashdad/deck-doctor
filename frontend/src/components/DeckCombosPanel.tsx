"use client";

/**
 * SP7 — combos in / near the current deck. SCAFFOLD — implement per roadmap §7.6.
 *
 * Chrome: copy SuggestionsPanel.tsx (backdrop + right panel w-[460px], z-[120]/[125]).
 * Opened from a header button `♾ Combos` in page.tsx (enabled when deck non-empty).
 *
 * Data: react-query keyed on the deck signature →
 *   postDeckCombos(entries, commanderId) (commander counts as in-deck server-side).
 *
 * Render:
 * - Section "In your deck" (data.complete): per combo — row of member art thumbnails
 *   (h-14 w-10 rounded, same as SuggestionsPanel), "→ {produces.join(', ')}" line in
 *   text-accent, popularity ("{popularity} decks") muted; empty state "No complete combos."
 * - Section "One card away" (data.near): per row — the MISSING card as a CardTile
 *   (compact, badge "missing", onAdd={() => add(missing)}) with amber border
 *   (this is the killer feature — make it loud), beside it the combo's produces line and
 *   the present members as small name chips.
 * - Clicking a member thumb / missing tile (not its add) →
 *   useRelationshipStore.open(card, "synergy").
 * data-testid: "deck-combos-panel", sections "combos-complete" / "combos-near".
 */
import type { Card, DeckEntry } from "@/lib/types";

export function DeckCombosPanel({
  isOpen,
  onClose,
  commander,
  entries,
}: {
  isOpen: boolean;
  onClose: () => void;
  commander: Card | null;
  entries: DeckEntry[];
}) {
  if (!isOpen) return null;
  void onClose;
  void commander;
  void entries;
  // TODO(SP7): implement per the docstring above.
  return null;
}
