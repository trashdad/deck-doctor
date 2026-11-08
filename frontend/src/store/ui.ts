import { create } from "zustand";
import type { EngineKey } from "@/components/EngineColumn";
import type { Card, RelationshipAxis } from "@/lib/types";
import type { MenuModel } from "@/components/card/cardActions";
import type { Rect } from "@/store/preview";

export type SearchTab = "search" | "commanders";

// ---- UX framework (plan §7.3) ----
export type RailTab = "suggest" | "cuts" | "tuneup" | "combos" | "pivot";
export type RailView =
  | { kind: "tab"; tab: RailTab }
  | { kind: "explorer"; card: Card; axis: RelationshipAxis | "combos" }
  | { kind: "upgrade"; card: Card }
  | { kind: "semantic"; card: Card }
  | { kind: "template" };

export type CardContext =
  | "find"
  | "deck"
  | "commander"
  | "suggest"
  | "cut"
  | "tuneup"
  | "combos"
  | "explorer"
  // Pivot-tab candidate commanders: no "Add to deck"/"Remove" (they are not deck cards);
  // buildCardActions still offers "Set as commander" plus the explore/external items.
  | "pivot";

export interface MenuOpenRequest {
  model: MenuModel;
  title: string;
  subtitle?: string;
  at: { x: number; y: number } | { anchorRect: Rect; surfaceRect: Rect };
  returnFocusTo: HTMLElement | null;
  /** How it was opened — decides initial focus (keyboard → first item). */
  via: "pointer" | "keyboard";
}

export interface SheetRequest {
  card: Card;
  context: CardContext;
  model: MenuModel;
}

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
  /** Non-null while the Engine Staples panel is open. */
  engineStaples: EngineStaplesTarget | null;
  openEngineStaples: (target: EngineStaplesTarget) => void;
  closeEngineStaples: () => void;
  /** True while the Win Conditions helper ("Build around these") panel is open. */
  winconHelperOpen: boolean;
  openWinconHelper: () => void;
  closeWinconHelper: () => void;

  // ---- UX framework (plan §7.3) ----
  railTab: RailTab;
  setRailTab: (t: RailTab) => void;
  /** Pushed views inside the rail (explorer, upgrade, semantic, template). */
  railStack: RailView[];
  pushRail: (v: RailView) => void;
  popRail: () => void;
  resetRail: () => void;
  /** The singleton context menu's open request (null = closed). */
  menu: MenuOpenRequest | null;
  openMenu: (req: MenuOpenRequest) => void;
  closeMenu: () => void;
  /** The singleton touch card sheet (null = closed). */
  sheet: SheetRequest | null;
  openSheet: (req: SheetRequest) => void;
  closeSheet: () => void;
  /** < 1024 px (plan §4.9): the rail is a bottom sheet opened from the tab bar. */
  railSheetOpen: boolean;
  setRailSheetOpen: (v: boolean) => void;
  /** < 1024 px: the Find panel is a full-height overlay opened from the header. */
  mobileFindOpen: boolean;
  setMobileFindOpen: (v: boolean) => void;
}

export const useUI = create<UIState>((set) => ({
  railTab: "suggest",
  setRailTab: (t) => set({ railTab: t, railStack: [] }),
  railStack: [],
  pushRail: (v) => set((s) => ({ railStack: [...s.railStack, v] })),
  popRail: () => set((s) => ({ railStack: s.railStack.slice(0, -1) })),
  resetRail: () => set({ railStack: [] }),
  menu: null,
  openMenu: (req) => set({ menu: req }),
  closeMenu: () => set({ menu: null }),
  sheet: null,
  openSheet: (req) => set({ sheet: req }),
  closeSheet: () => set({ sheet: null }),
  railSheetOpen: false,
  setRailSheetOpen: (v) => set({ railSheetOpen: v }),
  mobileFindOpen: false,
  setMobileFindOpen: (v) => set({ mobileFindOpen: v }),

  searchTab: "commanders",
  setSearchTab: (t) => set({ searchTab: t }),
  partnerPick: false,
  setPartnerPick: (v) => set({ partnerPick: v }),
  engineStaples: null,
  openEngineStaples: (target) => set({ engineStaples: target }),
  closeEngineStaples: () => set({ engineStaples: null }),
  winconHelperOpen: false,
  openWinconHelper: () => set({ winconHelperOpen: true }),
  closeWinconHelper: () => set({ winconHelperOpen: false }),
}));
