import { create } from "zustand";

export type SearchTab = "search" | "commanders";

interface UIState {
  /** Which tab the left search panel shows. Defaults to the commander list. */
  searchTab: SearchTab;
  setSearchTab: (t: SearchTab) => void;
}

export const useUI = create<UIState>((set) => ({
  searchTab: "commanders",
  setSearchTab: (t) => set({ searchTab: t }),
}));
