/**
 * Design tokens — single source for z-index, timing, sizes and role hues.
 * `tokens.css` mirrors these values as CSS variables (keep the two in sync by
 * hand; the CSS file is imported by globals.css).
 *
 * Numbers come from docs/plans/2026-11-05-ux-direction-and-plan.md §4.7 / §7.2.
 */
import type { Zone } from "@/lib/zones";

export const Z = {
  base: 0,
  lane: 10,
  lifted: 20,
  rail: 30,
  dialog: 100,
  preview: 200,
  menu: 300,
  sheet: 300,
  toast: 400,
} as const;

export const TIMING = {
  /** Hover-intent delay before a preview opens. */
  hoverOpen: 120,
  /** Delay after leaving the anchor before the preview closes. */
  hoverClose: 150,
  /** Warm window after a close inside which a new hover opens at 0 ms. */
  warmWindow: 250,
  /** Delay after keyboard focus before a preview opens. */
  focusOpen: 250,
  longPress: 450,
  previewFade: 90,
  menuFade: 80,
  reflow: 120,
  toast: 4000,
} as const;

export const SIZE = {
  previewMin: 240,
  previewMax: 336,
  previewVw: 22,
  previewMaxVh: 70,
  previewGap: 12,
  menuW: 248,
  menuItemH: 36,
  sheetRowH: 44,
  /** Anchor hit-box grows by this on every side. */
  tolerancePx: 6,
  /** Max gap between two cards of one surface that counts as "adjacent". */
  surfaceGapPx: 24,
  viewportInset: 8,
} as const;

/** Semantic colours (tokens.css `--ink` … `--warn`). One hue, one job (§3.4). */
export const COLOR = {
  ink: "#0a0420",
  panel: "#150d33",
  edge: "#3b2a66",
  accent: "#ffd24a",
  cyan: "#00eeff",
  text: "#e4e4e7",
  muted: "#a1a1aa",
  danger: "#ef4444",
  warn: "#f97316",
} as const;

/** Three sizes max (§3.2): label 11, body 13, numbers that matter 20. */
export const FONT_SIZE = {
  label: 11,
  body: 13,
  num: 20,
} as const;

/** Real MTG card aspect ratio (Scryfall "normal" images are 488×680). */
export const CARD_RATIO = 680 / 488;

export const ROLE_HUE: Record<Zone, string> = {
  Lands: "#9aa0a6",
  Ramp: "#22c55e",
  "Card Draw": "#3b82f6",
  Removal: "#ef4444",
  "Board Wipes": "#f97316",
  Counters: "#8b5cf6",
  Tokens: "#14b8a6",
  Utility: "#a1a1aa",
  "Win Conditions": "#ffd24a",
  Commanders: "#ffd24a",
};
