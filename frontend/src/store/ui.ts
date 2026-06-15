import { create } from "zustand";

export type SearchTab = "search" | "commanders";

interface UIState {
  /** Which tab the left search panel shows. Defaults to the commander list. */
  searchTab: SearchTab;
  setSearchTab: (t: SearchTab) => void;
  /** True while the user is picking a second (partner) commander. */
  partnerPick: boolean;
  setPartnerPick: (v: boolean) => void;
  /** True while a card right-click/click menu is open — suppresses the big hover
   * blow-up so it never covers the menu (the menu can open from any zone). */
  cardMenuOpen: boolean;
  setCardMenuOpen: (v: boolean) => void;
}

export const useUI = create<UIState>((set) => ({
  searchTab: "commanders",
  setSearchTab: (t) => set({ searchTab: t }),
  partnerPick: false,
  setPartnerPick: (v) => set({ partnerPick: v }),
  cardMenuOpen: false,
  setCardMenuOpen: (v) => set({ cardMenuOpen: v }),
}));
