import { create } from "zustand";
import type { EngineKey } from "@/components/EngineColumn";

export type SearchTab = "search" | "commanders";

export interface EngineStaplesTarget {
  engineKey: EngineKey;
  themeId: string;
  themeLabel: string;
}

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
  /** Non-null while the Engine Staples panel is open. */
  engineStaples: EngineStaplesTarget | null;
  openEngineStaples: (target: EngineStaplesTarget) => void;
  closeEngineStaples: () => void;
  /** True while the Win Conditions helper ("Build around these") panel is open. */
  winconHelperOpen: boolean;
  openWinconHelper: () => void;
  closeWinconHelper: () => void;
}

export const useUI = create<UIState>((set) => ({
  searchTab: "commanders",
  setSearchTab: (t) => set({ searchTab: t }),
  partnerPick: false,
  setPartnerPick: (v) => set({ partnerPick: v }),
  cardMenuOpen: false,
  setCardMenuOpen: (v) => set({ cardMenuOpen: v }),
  engineStaples: null,
  openEngineStaples: (target) => set({ engineStaples: target }),
  closeEngineStaples: () => set({ engineStaples: null }),
  winconHelperOpen: false,
  openWinconHelper: () => set({ winconHelperOpen: true }),
  closeWinconHelper: () => set({ winconHelperOpen: false }),
}));
