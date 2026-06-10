import { create } from "zustand";
import type { Card } from "@/lib/types";
import { autoZone, type Zone } from "@/lib/zones";

export interface DeckCard {
  card: Card;
  zone: Zone;
}

export interface BasicEntry {
  card: Card;
  quantity: number;
}

interface DeckState {
  cards: Record<string, DeckCard>; // keyed by card id (singletons)
  basics: Record<string, BasicEntry>; // basic lands with multiplicity
  add: (card: Card) => void;
  remove: (id: string) => void;
  move: (id: string, zone: Zone) => void;
  setBasic: (id: string, quantity: number, card?: Card) => void;
  clear: () => void;
}

export const useDeck = create<DeckState>((set) => ({
  cards: {},
  basics: {},
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
  setBasic: (id, quantity, card) =>
    set((s) => {
      const next = { ...s.basics };
      if (quantity <= 0) {
        delete next[id];
      } else {
        const existing = next[id];
        const c = card ?? existing?.card;
        if (!c) return s; // need a Card to render the first time
        next[id] = { card: c, quantity };
      }
      return { basics: next };
    }),
  clear: () => set({ cards: {}, basics: {} }),
}));
