import { create } from "zustand";
import type { Card } from "@/lib/types";
import { getSimilarCards, getComboCards } from "@/lib/api";

export type LookupMode = "similar" | "combos";

interface CardLookupState {
  isOpen: boolean;
  mode: LookupMode;
  sourceCard: Card | null;
  results: Card[] | null;
  loading: boolean;

  open: (card: Card, mode: LookupMode) => Promise<void>;
  close: () => void;
}

export const useCardLookupStore = create<CardLookupState>((set) => ({
  isOpen: false,
  mode: "similar",
  sourceCard: null,
  results: null,
  loading: false,

  open: async (card, mode) => {
    set({ isOpen: true, mode, sourceCard: card, results: null, loading: true });
    try {
      const cards =
        mode === "similar"
          ? await getSimilarCards(card.id, 30)
          : await getComboCards(card.id, 30);
      set({ results: cards, loading: false });
    } catch {
      set({ results: [], loading: false });
    }
  },

  close: () => set({ isOpen: false, sourceCard: null, results: null }),
}));
