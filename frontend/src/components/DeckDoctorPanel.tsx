"use client";

/**
 * SP8 — Deck Doctor panel (complete + cuts). SCAFFOLD — implement per roadmap §8.5.
 *
 * Chrome: SuggestionsPanel clone, header button `🩺 Doctor` (enabled when commander set).
 *
 * Two actions (tab-like toggle at the top: "Complete" | "Cuts"):
 * - Complete: button "Complete my deck" → postDeckComplete(entries, commanderId) →
 *   preview grouped by zone (zone header + rows: name, ×quantity, reason muted) +
 *   summary "adds N cards → 100". "Apply" button:
 *     nonbasics → useDeck.add(card) then move(card.id, zone);
 *     basics    → useDeck basics record (SP8 adds `basics: Record<string, number>` +
 *                 setBasic(id, n) to store/deck.ts, rendered in the Lands ZoneColumn as
 *                 `Mountain ×8` with +/− steppers; entries builders in page.tsx and the
 *                 SP6 save path must include basics with their quantity).
 * - Cuts: button "Suggest cuts" → postDeckCuts(entries, commanderId, 10) → worst-first
 *   list: name, contribution bar (width = contribution/maxContribution), reason chips
 *   (reuse SuggestionsPanel's ReasonChips — export it from SuggestionsPanel.tsx), and a
 *   red "Remove" button → useDeck.remove(id) (row disappears).
 * data-testid: "doctor-panel", "doctor-complete", "doctor-apply", "doctor-cuts".
 */
import type { Card, DeckEntry } from "@/lib/types";

export function DeckDoctorPanel({
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
  // TODO(SP8): implement per the docstring above.
  return null;
}
