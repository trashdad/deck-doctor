import type { ReactNode } from "react";

/**
 * The one menu icon set (visual review #9): 16 px box, 1.5 px stroke, round
 * caps/joins, `currentColor` — so every row's glyph has the same optical size
 * and weight and takes the gutter's muted colour. Pre-built elements so the
 * data-only action list (cardActions.ts) can reference them without JSX.
 */
export type MenuIconName =
  | "add"
  | "remove"
  | "commander"
  | "partner"
  | "move"
  | "cut"
  | "upgrade"
  | "why"
  | "similar"
  | "synergy"
  | "played"
  | "combos"
  | "semantic"
  | "scryfall"
  | "buy"
  | "check"
  | "chevron";

const PATHS: Record<MenuIconName, string> = {
  add: "M8 3v10M3 8h10",
  remove: "M4 4l8 8M12 4l-8 8",
  commander: "M2.5 12.5h11M2.5 12.5V5l3.5 3L8 3.5 10 8l3.5-3v7.5",
  partner: "M9 8a3 3 0 1 1-6 0 3 3 0 0 1 6 0zM10.5 5.2a3 3 0 1 1 0 5.6",
  move: "M2.5 8h11M9.5 4l4 4-4 4",
  cut: "M6.5 4a2 2 0 1 1-4 0 2 2 0 0 1 4 0zM6.5 12a2 2 0 1 1-4 0 2 2 0 0 1 4 0zM6 5.5l7.5 6M6 10.5l7.5-6",
  upgrade: "M8 13.5v-11M4 6.5l4-4 4 4",
  why: "M14 8A6 6 0 1 1 2 8a6 6 0 0 1 12 0zM6.2 6.3a1.9 1.9 0 1 1 2.7 1.9c-.6.3-.9.7-.9 1.3M8 11.6h.01",
  similar: "M2.5 3.5a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1h-6a1 1 0 0 1-1-1zM6 13.5h6.5a1 1 0 0 0 1-1V6",
  synergy: "M9 2 4 9h4l-1 5 5-7H8z",
  played: "M2.5 4.5a1 1 0 0 1 1-1h9a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1h-9a1 1 0 0 1-1-1zM2.5 7.5h11M7 7.5v5",
  combos: "M8 2l5.2 3v6L8 14l-5.2-3V5zM8 6.5v3M6.7 8h2.6",
  semantic: "M12.5 7a5.5 5.5 0 1 1-11 0 5.5 5.5 0 0 1 11 0zM11 11l3 3M7 4.5v5M4.5 7h5",
  scryfall: "M13 3l-7 7M7.5 3H13v5.5M11 9.5V13H3V5h3.5",
  buy: "M8 2v12M10.5 4.5H7.25a1.75 1.75 0 0 0 0 3.5h1.5a1.75 1.75 0 0 1 0 3.5H5",
  check: "M3 8.5l3 3 7-7",
  chevron: "M6 3.5 10.5 8 6 12.5",
};

export function MenuIcon({ name, size = 16 }: { name: MenuIconName; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      data-icon={name}
      style={{ display: "block", margin: "0 auto" }}
    >
      <path d={PATHS[name]} />
    </svg>
  );
}

/** Pre-built elements for the data-only action model. */
export const ICONS: Record<MenuIconName, ReactNode> = Object.fromEntries(
  (Object.keys(PATHS) as MenuIconName[]).map((n) => [n, <MenuIcon key={n} name={n} />]),
) as Record<MenuIconName, ReactNode>;
