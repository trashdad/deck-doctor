import { create } from "zustand";
import { TIMING } from "@/ui/tokens";

export interface ToastModel {
  id: number;
  message: string;
  /** Optional action button (e.g. "Undo"). */
  action?: { label: string; onClick: () => void };
  /** ms; defaults to TIMING.toast. */
  duration?: number;
}

interface ToastState {
  toasts: ToastModel[];
  push: (t: Omit<ToastModel, "id">) => number;
  dismiss: (id: number) => void;
}

let seq = 0;

export const useToasts = create<ToastState>((set) => ({
  toasts: [],
  push: (t) => {
    const id = ++seq;
    set((s) => ({ toasts: [...s.toasts.slice(-2), { ...t, id }] }));
    const ms = t.duration ?? TIMING.toast;
    if (ms > 0 && typeof window !== "undefined") {
      window.setTimeout(() => {
        set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) }));
      }, ms);
    }
    return id;
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) })),
}));

/** Imperative helper for non-React callers (stores, hooks). */
export function toast(t: Omit<ToastModel, "id">): number {
  return useToasts.getState().push(t);
}
