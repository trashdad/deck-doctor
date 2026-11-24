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
/** Auto-dismiss timers, cleared on manual dismiss (review F-24). */
const timers = new Map<number, number>();

export const useToasts = create<ToastState>((set) => ({
  toasts: [],
  push: (t) => {
    const id = ++seq;
    set((s) => ({ toasts: [...s.toasts.slice(-2), { ...t, id }] }));
    const ms = t.duration ?? TIMING.toast;
    if (ms > 0 && typeof window !== "undefined") {
      timers.set(
        id,
        window.setTimeout(() => {
          timers.delete(id);
          set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) }));
        }, ms),
      );
    }
    return id;
  },
  dismiss: (id) => {
    const t = timers.get(id);
    if (t !== undefined) window.clearTimeout(t);
    timers.delete(id);
    set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) }));
  },
}));

/** Imperative helper for non-React callers (stores, hooks). */
export function toast(t: Omit<ToastModel, "id">): number {
  return useToasts.getState().push(t);
}
