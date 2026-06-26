import { create } from "zustand";
import type { Card } from "@/lib/types";

/**
 * UI state for the Card Upgrade Finder panel. Store-backed (like the relationship
 * explorer) so any card menu can open it without threading props through the tree.
 * The panel itself reads the working deck + commander from the deck store and runs
 * the query; this store only holds the target card and the control knobs.
 */
interface UpgradeState {
  isOpen: boolean;
  target: Card | null;
  efficiency: number; // 0 = closest functional match, 1 = max efficiency
  favorSynergy: boolean;
  favorFlexibility: boolean;

  open: (card: Card) => void;
  close: () => void;
  setEfficiency: (v: number) => void;
  toggleSynergy: () => void;
  toggleFlexibility: () => void;
}

export const useUpgradeStore = create<UpgradeState>((set) => ({
  isOpen: false,
  target: null,
  efficiency: 0.5,
  favorSynergy: false,
  favorFlexibility: false,

  open: (card) => set({ isOpen: true, target: card }),
  close: () => set({ isOpen: false, target: null }),
  setEfficiency: (v) => set({ efficiency: Math.max(0, Math.min(1, v)) }),
  toggleSynergy: () => set((s) => ({ favorSynergy: !s.favorSynergy })),
  toggleFlexibility: () => set((s) => ({ favorFlexibility: !s.favorFlexibility })),
}));
