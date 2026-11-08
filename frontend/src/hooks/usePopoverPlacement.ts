"use client";

import { useEffect, useMemo, useState } from "react";
import type { Rect } from "@/store/preview";
import { CARD_RATIO, SIZE } from "@/ui/tokens";

/*
 * Placement maths for the preview, the context menu and the IER tooltip.
 *
 * Hand-rolled instead of @floating-ui (plan §7.6 fallback): the preview's main
 * axis is measured from the *surface* rect (the list the pointer is in) while
 * its cross axis follows the *anchor* rect (the card) — two reference rects,
 * which floating-ui's flip/shift middleware does not model without a custom
 * middleware of about the same size as this file. Pure functions below are
 * exercised by the /dev/ui-kit placement cases.
 */

export type Side = "right" | "left" | "below" | "above";

export interface Size {
  width: number;
  height: number;
}

export interface Viewport {
  width: number;
  height: number;
}

export interface Placement {
  x: number;
  y: number;
  side: Side;
  /** False when no candidate fit and the largest-visible-area fallback was used. */
  fits: boolean;
}

export const DEFAULT_ORDER: Side[] = ["right", "left", "below", "above"];

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

/** Preview size per §4.7.1: width clamp(240px, 22vw, 336px); 488:680; ≤ 70 vh. */
export function previewSize(vp: Viewport): Size {
  let width = clamp((SIZE.previewVw / 100) * vp.width, SIZE.previewMin, SIZE.previewMax);
  let height = width * CARD_RATIO;
  const maxH = (SIZE.previewMaxVh / 100) * vp.height;
  if (height > maxH) {
    height = maxH;
    width = height / CARD_RATIO;
  }
  return { width: Math.round(width), height: Math.round(height) };
}

function candidate(
  side: Side,
  anchor: Rect,
  surface: Rect,
  size: Size,
  vp: Viewport,
  inset: number,
  gap: number,
): { x: number; y: number } {
  const anchorCx = anchor.left + anchor.width / 2;
  const anchorCy = anchor.top + anchor.height / 2;
  switch (side) {
    case "right":
      return {
        x: surface.right + gap,
        y: clamp(anchorCy - size.height / 2, inset, vp.height - inset - size.height),
      };
    case "left":
      return {
        x: surface.left - gap - size.width,
        y: clamp(anchorCy - size.height / 2, inset, vp.height - inset - size.height),
      };
    case "below":
      return {
        x: clamp(anchorCx - size.width / 2, inset, vp.width - inset - size.width),
        y: anchor.bottom + gap,
      };
    case "above":
      return {
        x: clamp(anchorCx - size.width / 2, inset, vp.width - inset - size.width),
        y: anchor.top - gap - size.height,
      };
  }
}

function visibleArea(x: number, y: number, size: Size, vp: Viewport, inset: number): number {
  const l = Math.max(x, inset);
  const t = Math.max(y, inset);
  const r = Math.min(x + size.width, vp.width - inset);
  const b = Math.min(y + size.height, vp.height - inset);
  return Math.max(0, r - l) * Math.max(0, b - t);
}

function fitsViewport(x: number, y: number, size: Size, vp: Viewport, inset: number): boolean {
  return (
    x >= inset &&
    y >= inset &&
    x + size.width <= vp.width - inset &&
    y + size.height <= vp.height - inset
  );
}

export interface PlaceInput {
  anchor: Rect;
  surface: Rect;
  size: Size;
  viewport: Viewport;
  inset?: number;
  gap?: number;
  order?: Side[];
}

/**
 * Surface-aware placement (§4.7.1): the first candidate in `order` that fits
 * the viewport (inset) wins; otherwise the candidate with the largest visible
 * area, shifted along its cross axis into the viewport.
 */
export function computePlacement(input: PlaceInput): Placement {
  const inset = input.inset ?? SIZE.viewportInset;
  const gap = input.gap ?? SIZE.previewGap;
  const order = input.order ?? DEFAULT_ORDER;
  const { anchor, surface, size, viewport } = input;

  for (const side of order) {
    const p = candidate(side, anchor, surface, size, viewport, inset, gap);
    if (fitsViewport(p.x, p.y, size, viewport, inset)) return { ...p, side, fits: true };
  }

  let best: Placement | null = null;
  let bestArea = -1;
  for (const side of order) {
    const p = candidate(side, anchor, surface, size, viewport, inset, gap);
    const area = visibleArea(p.x, p.y, size, viewport, inset);
    if (area > bestArea) {
      bestArea = area;
      best = { ...p, side, fits: false };
    }
  }
  const b = best!;
  // Shift along the cross axis (and clamp the main axis) so as much as possible shows.
  return {
    ...b,
    x: clamp(b.x, inset, Math.max(inset, viewport.width - inset - size.width)),
    y: clamp(b.y, inset, Math.max(inset, viewport.height - inset - size.height)),
  };
}

/** Pointer-anchored menu: at (x, y), flipped/shifted to stay inside the inset viewport. */
export function computePointerPlacement(
  at: { x: number; y: number },
  size: Size,
  viewport: Viewport,
  inset: number = SIZE.viewportInset,
): { x: number; y: number } {
  let x = at.x;
  let y = at.y;
  if (x + size.width > viewport.width - inset) x = at.x - size.width; // flip left
  if (y + size.height > viewport.height - inset) y = at.y - size.height; // flip up
  x = clamp(x, inset, Math.max(inset, viewport.width - inset - size.width));
  y = clamp(y, inset, Math.max(inset, viewport.height - inset - size.height));
  return { x, y };
}

/**
 * Keyboard-opened menu (§4.7.3): below-start of the anchor; if that would cover
 * the anchor's own surface by more than half, place beside the surface instead.
 */
export function computeKeyboardMenuPlacement(
  anchor: Rect,
  surface: Rect,
  size: Size,
  viewport: Viewport,
  inset: number = SIZE.viewportInset,
): Placement {
  const below = { x: anchor.left, y: anchor.bottom + 4 };
  const ix = Math.max(0, Math.min(below.x + size.width, surface.right) - Math.max(below.x, surface.left));
  const iy = Math.max(0, Math.min(below.y + size.height, surface.bottom) - Math.max(below.y, surface.top));
  const coverage = (ix * iy) / Math.max(1, surface.width * surface.height);
  if (coverage <= 0.5 && fitsViewport(below.x, below.y, size, viewport, inset)) {
    return { ...below, side: "below", fits: true };
  }
  return computePlacement({ anchor, surface, size, viewport, inset, gap: 4 });
}

export function getViewport(): Viewport {
  if (typeof window === "undefined") return { width: 1440, height: 900 };
  return { width: window.innerWidth, height: window.innerHeight };
}

/**
 * Re-computes `compute()` on scroll (capture) and resize. `compute` must be
 * cheap and pure over the DOM — the hook just supplies the tick.
 */
export function usePopoverPlacement<T>(
  compute: () => T | null,
  deps: ReadonlyArray<unknown>,
): T | null {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const bump = () => setTick((t) => t + 1);
    window.addEventListener("scroll", bump, { capture: true, passive: true });
    window.addEventListener("resize", bump, { passive: true });
    return () => {
      window.removeEventListener("scroll", bump, { capture: true });
      window.removeEventListener("resize", bump);
    };
  }, []);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(() => compute(), [tick, ...deps]);
}
