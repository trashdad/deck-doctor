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
      const zone = autoZone(card);
      const cards = { ...s.cards, [card.id]: { card, zone } };

      // Selecting a commander enforces Commander color-identity: any card whose
      // color identity isn't a subset of the commander(s)' becomes illegal and is
      // dropped. (Union of all Commanders-zone cards handles partner pairs.)
      if (zone === "Commanders") {
        const ci = new Set<string>();
        for (const dc of Object.values(cards)) {
          if (dc.zone === "Commanders") (dc.card.color_identity ?? []).forEach((c) => ci.add(c));
        }
        const legal = (c: Card) => (c.color_identity ?? []).every((col) => ci.has(col));
        const prunedCards = Object.fromEntries(
          Object.entries(cards).filter(([, dc]) => dc.zone === "Commanders" || legal(dc.card)),
        );
        const prunedBasics = Object.fromEntries(
          Object.entries(s.basics).filter(([, be]) => legal(be.card)),
        );
        return { cards: prunedCards, basics: prunedBasics };
      }
      return { cards };
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
