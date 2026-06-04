import { create } from "zustand";
import type { Card } from "@/lib/types";
import { autoZone, type Zone } from "@/lib/zones";

export interface DeckCard {
  card: Card;
  zone: Zone;
}

interface DeckState {
  cards: Record<string, DeckCard>; // keyed by card id
  add: (card: Card) => void;
  remove: (id: string) => void;
  move: (id: string, zone: Zone) => void;
  clear: () => void;
}

export const useDeck = create<DeckState>((set) => ({
  cards: {},
  add: (card) =>
    set((s) => {
      if (s.cards[card.id]) return s;
      return { cards: { ...s.cards, [card.id]: { card, zone: autoZone(card) } } };
    }),
  remove: (id) =>
    set((s) => {
      const next = { ...s.cards };
      delete next[id];
      return { cards: next };
    }),
  move: (id, zone) =>
    set((s) => {
      const dc = s.cards[id];
      if (!dc) return s;
      return { cards: { ...s.cards, [id]: { ...dc, zone } } };
    }),
  clear: () => set({ cards: {} }),
}));
