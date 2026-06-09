import { create } from "zustand";
import type { Card } from "@/lib/types";
import type { CardSemantics } from "@/lib/api";
import { getCardSemantics, searchBySemantics } from "@/lib/api";

interface SemanticState {
  isOpen: boolean;
  activeCard: Card | null;
  semantics: CardSemantics | null;
  loading: boolean;
  selectedTags: Set<string>;
  linkedTags: Set<string>;   // subset of selectedTags that must co-appear on same ability
  results: Card[] | null;
  searching: boolean;

  openCard: (card: Card) => Promise<void>;
  close: () => void;
  toggleTag: (tag: string) => void;
  toggleLinked: (tag: string) => void;
  runSearch: () => Promise<void>;
  clearResults: () => void;
}

export const useSemanticStore = create<SemanticState>((set, get) => ({
  isOpen: false,
  activeCard: null,
  semantics: null,
  loading: false,
  selectedTags: new Set(),
  linkedTags: new Set(),
  results: null,
  searching: false,

  openCard: async (card) => {
    set({
      isOpen: true,
      activeCard: card,
      semantics: null,
      loading: true,
      selectedTags: new Set(),
      linkedTags: new Set(),
      results: null,
    });
    try {
      const sem = await getCardSemantics(card.id);
      set({ semantics: sem, loading: false });
    } catch {
      set({ loading: false });
    }
  },

  close: () =>
    set({
      isOpen: false,
      activeCard: null,
      semantics: null,
      selectedTags: new Set(),
      linkedTags: new Set(),
      results: null,
    }),

  toggleTag: (tag) =>
    set((state) => {
      const sel = new Set(state.selectedTags);
      const lnk = new Set(state.linkedTags);
      if (sel.has(tag)) {
        sel.delete(tag);
        lnk.delete(tag);
      } else {
        sel.add(tag);
      }
      return { selectedTags: sel, linkedTags: lnk, results: null };
    }),

  toggleLinked: (tag) =>
    set((state) => {
      const lnk = new Set(state.linkedTags);
      if (lnk.has(tag)) {
        lnk.delete(tag);
      } else {
        lnk.add(tag);
      }
      return { linkedTags: lnk };
    }),

  runSearch: async () => {
    const { selectedTags, linkedTags } = get();
    if (selectedTags.size === 0) return;
    set({ searching: true, results: null });
    const linkedArr = [...linkedTags];
    const flatArr = [...selectedTags].filter((t) => !linkedTags.has(t));
    try {
      const cards = await searchBySemantics({
        linkedTags: linkedArr,
        flatTags: flatArr,
        limit: 60,
      });
      set({ results: cards, searching: false });
    } catch {
      set({ searching: false, results: [] });
    }
  },

  clearResults: () => set({ results: null }),
}));
