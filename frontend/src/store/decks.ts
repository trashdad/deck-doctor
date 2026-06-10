/**
 * SP6 — saved-deck client state. SCAFFOLD — implement per roadmap §6.5
 * (docs/superpowers/plans/2026-06-10-sp6-sp11-roadmap.md).
 *
 * Contract:
 * - refresh(): GET /decks -> deckList.
 * - saveCurrent(name?): if currentId === null -> saveDeck(...) (POST) and set currentId;
 *   else updateDeck(currentId, ...). Cards come from useDeck.getState().cards
 *   (zone per entry, quantity 1) PLUS useDeck basics (SP8 adds a basics record —
 *   include {id, zone: "Lands", quantity} rows for it once it exists).
 * - load(id): getDeck(id) -> repopulate useDeck: clear(), then per row add(row.card)
 *   followed by move(row.card.id, row.zone); set currentId, dirty=false.
 * - remove(id): deleteDeck(id); if id === currentId, currentId = null.
 * - markDirty(): dirty = true (page.tsx autosave effect debounces 2000 ms -> saveCurrent()
 *   when currentId !== null).
 * - Autosave snapshot: page.tsx also writes localStorage "simmander.autosave" on every deck
 *   change and offers a one-time restore on boot when the deck store is empty.
 */
import { create } from "zustand";
import type { DeckSummary } from "@/lib/types";

interface DecksState {
  deckList: DeckSummary[];
  currentId: string | null;
  dirty: boolean;

  refresh: () => Promise<void>;
  saveCurrent: (name?: string) => Promise<void>;
  load: (id: string) => Promise<void>;
  remove: (id: string) => Promise<void>;
  markDirty: () => void;
}

export const useDecksStore = create<DecksState>(() => ({
  deckList: [],
  currentId: null,
  dirty: false,

  refresh: async () => {
    throw new Error("SP6 pending — roadmap §6.5");
  },
  saveCurrent: async () => {
    throw new Error("SP6 pending — roadmap §6.5");
  },
  load: async () => {
    throw new Error("SP6 pending — roadmap §6.5");
  },
  remove: async () => {
    throw new Error("SP6 pending — roadmap §6.5");
  },
  markDirty: () => {
    throw new Error("SP6 pending — roadmap §6.5");
  },
}));
