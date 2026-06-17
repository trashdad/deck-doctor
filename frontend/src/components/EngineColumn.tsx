"use client";

import type { ThemeInfo } from "@/lib/types";
import type { Zone } from "@/lib/zones";
import type { PileEntry } from "./CardPile";
import { FieldSection } from "./FieldSection";

export type EngineKey = "e1" | "e2" | "e3" | "neutral" | "single";

/** Sections to be rendered inside one engine column, keyed by Zone. */
export type ColumnSections = Partial<Record<Zone, PileEntry[]>>;

interface Props {
  engineKey: EngineKey;
  /** Display name for the engine (e.g. "Engine 1", "Neutral", or "" for single-column). */
  label?: string;
  /** Static theme label (e.g. "no engine" for the neutral column). */
  themeLabel?: string;
  /** When provided, renders a theme picker in the header (used by e1/e2/e3). */
  themeValue?: string;
  themeOptions?: ThemeInfo[];
  onThemeChange?: (id: string) => void;
  /** When provided, renders a Staples button in the header (only if a theme is selected). */
  onStaples?: () => void;
  sections: ColumnSections;
  onRemove?: (cardId: string) => void;
}

// Per-engine accent hues (Arcade Diagnosis): crimson e1 / sapphire e2 / emerald e3.
// `accent` = the engine's neon edge colour, used for the top rule + glow + number chip.
// Each engine carries a distinct 16-bit Golden-Axe weapon (sword/hammer/spear/
// dagger), shown as the header bullet + on its Staples button. Win Conditions keeps
// the double-bit axe (see EngineBoard).
const ENGINE_STYLES: Record<
  EngineKey,
  { border: string; bg: string; tint: string; headColor: string; accent: string; glow: string; weapon: string }
> = {
  e1: {
    border: "border-[#ff3b6b]/40",
    bg: "linear-gradient(180deg, rgba(255,59,107,0.13), rgba(18,9,46,0.6))",
    tint: "rgba(255,59,107,0.10)",
    headColor: "#ffe9a0",
    accent: "#ff3b6b",
    glow: "0 0 30px -8px #ff3b6b, inset 0 0 0 1px rgba(255,246,194,.03)",
    weapon: "/deck-doctor/weapons/sword.svg",
  },
  e2: {
    border: "border-[#3b7cff]/40",
    bg: "linear-gradient(180deg, rgba(59,124,255,0.13), rgba(18,9,46,0.6))",
    tint: "rgba(59,124,255,0.10)",
    headColor: "#ffe9a0",
    accent: "#3b7cff",
    glow: "0 0 30px -8px #3b7cff, inset 0 0 0 1px rgba(255,246,194,.03)",
    weapon: "/deck-doctor/weapons/hammer.svg",
  },
  e3: {
    border: "border-[#21ff9e]/40",
    bg: "linear-gradient(180deg, rgba(33,255,158,0.12), rgba(18,9,46,0.6))",
    tint: "rgba(33,255,158,0.10)",
    headColor: "#ffe9a0",
    accent: "#21ff9e",
    glow: "0 0 30px -8px #21ff9e, inset 0 0 0 1px rgba(255,246,194,.03)",
    weapon: "/deck-doctor/weapons/spear.svg",
  },
  neutral: {
    border: "border-edge",
    bg: "linear-gradient(180deg, rgba(120,120,140,0.08), rgba(0,0,0,0))",
    tint: "rgba(100,100,120,0.06)",
    headColor: "#c8b6ff",
    accent: "#9a4bff",
    glow: "inset 0 0 0 1px rgba(255,246,194,.03)",
    weapon: "/deck-doctor/weapons/dagger.svg",
  },
  single: {
    border: "border-accent/30",
    bg: "linear-gradient(180deg, rgba(43,15,84,0.5), rgba(18,9,46,0.5))",
    tint: "rgba(0,0,0,0)",
    headColor: "#ffd24a",
    accent: "#ffd24a",
    glow: "inset 0 0 0 1px rgba(255,246,194,.03)",
    weapon: "/deck-doctor/golden-axe.svg",
  },
};

/**
 * One engine column (red / blue / neutral / single).
 * Renders only the non-empty FieldSections from `sections`.
 */
export function EngineColumn({
  engineKey,
  label,
  themeLabel,
  themeValue,
  themeOptions,
  onThemeChange,
  onStaples,
  sections,
  onRemove,
}: Props) {
  const style = ENGINE_STYLES[engineKey];

  // Only render non-empty sections (progressive reveal)
  const nonEmptySections = (Object.entries(sections) as [Zone, PileEntry[]][]).filter(
    ([, entries]) => entries.length > 0,
  );

  if (nonEmptySections.length === 0 && engineKey !== "e1" && engineKey !== "e2" && engineKey !== "e3") {
    return null;
  }

  // Drop id prefix — must be unique across the whole board so dnd-kit
  // routes drops to the right section. In composite mode we prefix the engine.
  const dropPrefix = engineKey === "single" ? "" : `${engineKey}-`;

  const isEngine = engineKey === "e1" || engineKey === "e2" || engineKey === "e3";

  return (
    <div
      className={`flex flex-1 flex-col gap-2 rounded-xl border p-3 backdrop-blur-sm ${style.border}`}
      style={{
        background: style.bg,
        boxShadow: style.glow,
        // Per-engine neon top rule.
        borderTop: isEngine ? `3px solid ${style.accent}` : undefined,
      }}
      data-testid={`engine-col-${engineKey}`}
    >
      {/* Column header (composite / engine columns) */}
      {(label || onThemeChange) && (
        <div className="mb-1 flex flex-col gap-1.5 border-b border-accent/15 pb-2">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              {label && (
                <span className="flex items-center gap-2">
                  {/* This engine's distinct weapon as the header bullet. */}
                  {engineKey !== "single" && (
                    <span
                      className="inline-block bg-contain bg-no-repeat bg-center [image-rendering:pixelated]"
                      style={{
                        backgroundImage: `url(${style.weapon})`,
                        width: 16,
                        height: 20,
                        filter: `drop-shadow(0 0 6px ${style.accent})`,
                      }}
                    />
                  )}
                  <span
                    className="arcade-bevel text-sm tracking-wide"
                    style={{ textShadow: `1px 1px 0 #5e3510, 0 0 10px ${style.accent}` }}
                  >
                    {label}
                  </span>
                </span>
              )}
              {themeLabel && !onThemeChange && (
                <span className="text-xs text-[#9fd0ff]">{themeLabel}</span>
              )}
            </div>
            {onStaples && themeValue && (
              <button
                title="Engine Staples — top cards for this theme"
                data-testid={`staples-btn-${engineKey}`}
                onClick={onStaples}
                className="flex shrink-0 items-center gap-1 rounded border border-accent/45 bg-accent/5 px-1.5 py-0.5
                           text-[10px] font-semibold uppercase tracking-wide text-accent transition
                           hover:bg-accent/15 hover:shadow-neon"
              >
                <span
                  className="inline-block bg-contain bg-no-repeat bg-center [image-rendering:pixelated]"
                  style={{
                    backgroundImage: `url(${style.weapon})`,
                    width: 13,
                    height: 16,
                    filter: "drop-shadow(0 0 3px rgba(255,174,0,.8))",
                  }}
                />
                Staples
              </button>
            )}
          </div>
          {onThemeChange && themeOptions && (
            <select
              value={themeValue ?? ""}
              onChange={(e) => onThemeChange(e.target.value)}
              data-testid={`engine-theme-${engineKey}`}
              className="w-full rounded border border-accent/25 bg-black/40 px-1.5 py-1 text-xs
                         text-zinc-200 outline-none focus:border-accent/60 focus:shadow-neon"
            >
              <option value="">— pick a theme —</option>
              {themeOptions.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label}
                </option>
              ))}
            </select>
          )}
        </div>
      )}

      {/* Field subsections — only non-empty */}
      {nonEmptySections.length === 0 ? (
        <p className="py-4 text-center text-xs italic text-[#9fd0ff]/50">
          No cards match this engine yet
        </p>
      ) : (
        nonEmptySections.map(([zone, entries]) => (
          <FieldSection
            key={zone}
            zone={zone}
            dropId={`${dropPrefix}${zone}`}
            entries={entries}
            onRemove={onRemove}
            tint={style.tint}
          />
        ))
      )}
    </div>
  );
}
