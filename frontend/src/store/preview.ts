import { create } from "zustand";
import type { Card } from "@/lib/types";

/** A plain rect (DOMRect is not serialisable / comparable; we copy the numbers). */
export interface Rect {
  left: number;
  top: number;
  right: number;
  bottom: number;
  width: number;
  height: number;
}

export function toRect(r: DOMRect | Rect): Rect {
  return {
    left: r.left,
    top: r.top,
    right: r.right,
    bottom: r.bottom,
    width: r.width,
    height: r.height,
  };
}

export interface PreviewState {
  card: Card | null;
  anchorRect: Rect | null;
  surfaceRect: Rect | null;
  /** id of the anchor element (data-card-id) — exposed as data-anchor-id for tests. */
  anchorId: string | null;
  open: boolean;
  /** Epoch ms until which a new hover opens at 0 ms (tooltip-group behaviour). */
  warmUntil: number;
  /** Refcount: menus, sheets, dialogs and drags each hold one while open. */
  suppressed: number;
  show: (card: Card, anchor: DOMRect | Rect, surface: DOMRect | Rect, anchorId?: string) => void;
  /** Re-position the open preview (scroll/resize) without changing the card. */
  reposition: (anchor: DOMRect | Rect, surface: DOMRect | Rect) => void;
  hide: () => void;
  /** Suppress previews; returns the release function. Hides any open preview. */
  suppress: () => () => void;
}

export const usePreview = create<PreviewState>((set, get) => ({
  card: null,
  anchorRect: null,
  surfaceRect: null,
  anchorId: null,
  open: false,
  warmUntil: 0,
  suppressed: 0,
  show: (card, anchor, surface, anchorId) => {
    if (get().suppressed > 0) return;
    set({
      card,
      anchorRect: toRect(anchor),
      surfaceRect: toRect(surface),
      anchorId: anchorId ?? null,
      open: true,
    });
  },
  reposition: (anchor, surface) => {
    if (!get().open) return;
    set({ anchorRect: toRect(anchor), surfaceRect: toRect(surface) });
  },
  hide: () => {
    if (!get().open) return;
    set({ open: false, warmUntil: Date.now() + 250 });
  },
  suppress: () => {
    set((s) => ({ suppressed: s.suppressed + 1, open: false }));
    let released = false;
    return () => {
      if (released) return;
      released = true;
      set((s) => ({ suppressed: Math.max(0, s.suppressed - 1) }));
    };
  },
}));
