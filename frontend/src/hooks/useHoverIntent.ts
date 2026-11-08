"use client";

import { useCallback, useEffect, useRef } from "react";
import type { Card } from "@/lib/types";
import { usePreview } from "@/store/preview";
import { SIZE, TIMING } from "@/ui/tokens";

/*
 * Hover-intent controller for the singleton CardPreview (plan §4.7.1).
 *
 *   open      120 ms after pointer enter (mouse/pen only), cancelled on leave
 *   re-target 0 ms while a preview is open or within 250 ms of one closing
 *   close     150 ms after the pointer leaves the anchor + 6 px tolerance box;
 *             entering any card cancels the close (covers the ≤ 24 px gap rule)
 *   focus     250 ms after keyboard focus; blur / Esc hide immediately
 *
 * One module-level controller owns the timers so sweeping across cards never
 * races two per-card timers against each other.
 */

interface ActiveAnchor {
  el: HTMLElement;
  surfaceEl: HTMLElement;
  card: Card;
}

const ctl: {
  openT: number | null;
  closeT: number | null;
  focusT: number | null;
  active: ActiveAnchor | null;
  watch: ((e: PointerEvent) => void) | null;
} = { openT: null, closeT: null, focusT: null, active: null, watch: null };

function clearT(key: "openT" | "closeT" | "focusT") {
  const t = ctl[key];
  if (t !== null) {
    window.clearTimeout(t);
    ctl[key] = null;
  }
}

function stopWatch() {
  if (ctl.watch) {
    document.removeEventListener("pointermove", ctl.watch);
    ctl.watch = null;
  }
}

/** The element currently anchoring the preview (for re-measuring on scroll). */
export function getActiveAnchor(): ActiveAnchor | null {
  return ctl.active;
}

function findSurface(el: HTMLElement): HTMLElement {
  return (el.closest("[data-surface]") as HTMLElement | null) ?? el;
}

function showNow(el: HTMLElement, card: Card) {
  clearT("openT");
  clearT("closeT");
  clearT("focusT");
  stopWatch();
  const surfaceEl = findSurface(el);
  ctl.active = { el, surfaceEl, card };
  usePreview
    .getState()
    .show(card, el.getBoundingClientRect(), surfaceEl.getBoundingClientRect(), el.dataset.cardId);
}

export function hidePreviewNow() {
  clearT("openT");
  clearT("closeT");
  clearT("focusT");
  stopWatch();
  ctl.active = null;
  usePreview.getState().hide();
}

function inside(rect: DOMRect, x: number, y: number, pad: number): boolean {
  return x >= rect.left - pad && x <= rect.right + pad && y >= rect.top - pad && y <= rect.bottom + pad;
}

function scheduleClose() {
  clearT("closeT");
  ctl.closeT = window.setTimeout(() => {
    ctl.closeT = null;
    hidePreviewNow();
  }, TIMING.hoverClose);
}

export interface HoverIntentOptions {
  card: Card;
  /** False on touch devices / contexts without a preview. */
  enabled?: boolean;
}

export interface HoverIntentHandlers {
  onPointerEnter: (e: React.PointerEvent<HTMLElement>) => void;
  onPointerLeave: (e: React.PointerEvent<HTMLElement>) => void;
  onFocus: (e: React.FocusEvent<HTMLElement>) => void;
  onBlur: (e: React.FocusEvent<HTMLElement>) => void;
}

export function useHoverIntent({ card, enabled = true }: HoverIntentOptions): HoverIntentHandlers {
  const cardRef = useRef(card);
  cardRef.current = card;

  // If this anchor unmounts while it owns the preview, hide it.
  const elRef = useRef<HTMLElement | null>(null);
  useEffect(
    () => () => {
      if (ctl.active && ctl.active.el === elRef.current) hidePreviewNow();
    },
    [],
  );

  const onPointerEnter = useCallback(
    (e: React.PointerEvent<HTMLElement>) => {
      if (!enabled) return;
      if (e.pointerType !== "mouse" && e.pointerType !== "pen") return;
      const el = e.currentTarget;
      elRef.current = el;
      const st = usePreview.getState();
      if (st.suppressed > 0) return;
      clearT("closeT");
      clearT("focusT"); // pointer intent supersedes a pending focus-open
      stopWatch();
      if (ctl.active && ctl.active.el === el && st.open) return;
      const warm = st.open || Date.now() < st.warmUntil;
      if (warm) {
        showNow(el, cardRef.current);
        return;
      }
      clearT("openT");
      ctl.openT = window.setTimeout(() => {
        ctl.openT = null;
        showNow(el, cardRef.current);
      }, TIMING.hoverOpen);
    },
    [enabled],
  );

  const onPointerLeave = useCallback(
    (e: React.PointerEvent<HTMLElement>) => {
      if (!enabled) return;
      if (e.pointerType !== "mouse" && e.pointerType !== "pen") return;
      clearT("openT");
      const el = e.currentTarget;
      if (!ctl.active || ctl.active.el !== el || !usePreview.getState().open) return;
      const rect = el.getBoundingClientRect();
      if (inside(rect, e.clientX, e.clientY, SIZE.tolerancePx)) {
        // Slipped just off the card: keep it open until the pointer leaves the
        // 6 px tolerance box, then start the 150 ms close timer.
        stopWatch();
        ctl.watch = (m: PointerEvent) => {
          if (!inside(el.getBoundingClientRect(), m.clientX, m.clientY, SIZE.tolerancePx)) {
            stopWatch();
            scheduleClose();
          }
        };
        document.addEventListener("pointermove", ctl.watch, { passive: true });
        return;
      }
      scheduleClose();
    },
    [enabled],
  );

  const onFocus = useCallback(
    (e: React.FocusEvent<HTMLElement>) => {
      if (!enabled) return;
      const el = e.currentTarget;
      if (e.target !== el) return; // focus moved to an inner button
      elRef.current = el;
      let visible = true;
      try {
        visible = el.matches(":focus-visible");
      } catch {
        /* older engines */
      }
      if (!visible) return;
      clearT("focusT");
      ctl.focusT = window.setTimeout(() => {
        ctl.focusT = null;
        if (document.activeElement === el) showNow(el, cardRef.current);
      }, TIMING.focusOpen);
    },
    [enabled],
  );

  const onBlur = useCallback(
    (e: React.FocusEvent<HTMLElement>) => {
      if (!enabled) return;
      clearT("focusT");
      if (ctl.active && ctl.active.el === e.currentTarget) hidePreviewNow();
    },
    [enabled],
  );

  return { onPointerEnter, onPointerLeave, onFocus, onBlur };
}
