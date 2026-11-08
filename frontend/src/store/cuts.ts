import { create } from "zustand";

/**
 * Cut-candidate flags (client-side only). A flagged card shows a dashed red
 * ring + ✂ badge on the board until it is cut or unflagged (plan §4.2 / §4.5).
 */
interface CutsState {
  candidates: Set<string>;
  /** How many cards the Cuts tab is aiming to remove (deck count − 100, min 1). */
  target: number;
  toggle: (id: string) => void;
  has: (id: string) => boolean;
  setTarget: (n: number) => void;
  clear: () => void;
}

export const useCuts = create<CutsState>((set, get) => ({
  candidates: new Set(),
  target: 1,
  toggle: (id) =>
    set((s) => {
      const next = new Set(s.candidates);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return { candidates: next };
    }),
  has: (id) => get().candidates.has(id),
  setTarget: (n) => set({ target: Math.max(1, Math.floor(n)) }),
  clear: () => set({ candidates: new Set() }),
}));
