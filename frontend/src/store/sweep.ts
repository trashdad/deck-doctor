import { create } from "zustand";

/**
 * UI state for the deck-wide Upgrade Sweep ("Tune-up") panel. Store-backed so a
 * single header button can open it; the panel reads the working deck itself.
 */
interface SweepState {
  isOpen: boolean;
  efficiency: number; // 0 = closest functional match, 1 = max efficiency
  favorSynergy: boolean;

  open: () => void;
  close: () => void;
  setEfficiency: (v: number) => void;
  toggleSynergy: () => void;
}

export const useSweepStore = create<SweepState>((set) => ({
  isOpen: false,
  efficiency: 0.4,
  favorSynergy: true,

  open: () => set({ isOpen: true }),
  close: () => set({ isOpen: false }),
  setEfficiency: (v) => set({ efficiency: Math.max(0, Math.min(1, v)) }),
  toggleSynergy: () => set((s) => ({ favorSynergy: !s.favorSynergy })),
}));
