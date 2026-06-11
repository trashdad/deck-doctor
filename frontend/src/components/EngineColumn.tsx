"use client";

import type { ThemeInfo } from "@/lib/types";
import type { Zone } from "@/lib/zones";
import type { PileEntry } from "./CardPile";
import { FieldSection } from "./FieldSection";

export type EngineKey = "e1" | "e2" | "neutral" | "single";

/** Sections to be rendered inside one engine column, keyed by Zone. */
export type ColumnSections = Partial<Record<Zone, PileEntry[]>>;

interface Props {
  engineKey: EngineKey;
  /** Display name for the engine (e.g. "Engine 1", "Neutral", or "" for single-column). */
  label?: string;
  /** Static theme label (e.g. "no engine" for the neutral column). */
  themeLabel?: string;
  /** When provided, renders a theme picker in the header (used by e1/e2). */
  themeValue?: string;
  themeOptions?: ThemeInfo[];
  onThemeChange?: (id: string) => void;
  sections: ColumnSections;
  onRemove?: (cardId: string) => void;
}

const ENGINE_STYLES: Record<EngineKey, { border: string; bg: string; tint: string; headColor: string }> = {
  e1: {
    border: "border-red-500/30",
    bg: "linear-gradient(180deg, rgba(239,68,68,0.13), rgba(239,68,68,0.04))",
    tint: "rgba(239,68,68,0.08)",
    headColor: "#ef8a8a",
  },
  e2: {
    border: "border-blue-500/30",
    bg: "linear-gradient(180deg, rgba(59,132,246,0.13), rgba(59,132,246,0.04))",
    tint: "rgba(59,132,246,0.08)",
    headColor: "#8ab6ef",
  },
  neutral: {
    border: "border-zinc-500/20",
    bg: "linear-gradient(180deg, rgba(120,120,140,0.08), rgba(0,0,0,0))",
    tint: "rgba(100,100,120,0.06)",
    headColor: "#9a94b0",
  },
  single: {
    border: "border-edge",
    bg: "transparent",
    tint: "rgba(0,0,0,0)",
    headColor: "#c9a227",
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
  sections,
  onRemove,
}: Props) {
  const style = ENGINE_STYLES[engineKey];

  // Only render non-empty sections (progressive reveal)
  const nonEmptySections = (Object.entries(sections) as [Zone, PileEntry[]][]).filter(
    ([, entries]) => entries.length > 0,
  );

  if (nonEmptySections.length === 0 && engineKey !== "e1" && engineKey !== "e2") {
    return null;
  }

  // Drop id prefix — must be unique across the whole board so dnd-kit
  // routes drops to the right section. In composite mode we prefix the engine.
  const dropPrefix = engineKey === "single" ? "" : `${engineKey}-`;

  return (
    <div
      className={`flex flex-1 flex-col gap-2 rounded-xl border p-3 ${style.border}`}
      style={{ background: style.bg }}
      data-testid={`engine-col-${engineKey}`}
    >
      {/* Column header (composite / engine columns) */}
      {(label || onThemeChange) && (
        <div className="mb-1 flex flex-col gap-1.5 border-b border-white/[0.06] pb-2">
          <div className="flex items-baseline gap-2">
            {label && (
              <span
                className="font-display text-sm font-semibold tracking-wide"
                style={{ color: style.headColor }}
              >
                {label}
              </span>
            )}
            {themeLabel && !onThemeChange && (
              <span className="text-xs text-zinc-500">{themeLabel}</span>
            )}
          </div>
          {onThemeChange && themeOptions && (
            <select
              value={themeValue ?? ""}
              onChange={(e) => onThemeChange(e.target.value)}
              data-testid={`engine-theme-${engineKey}`}
              className="w-full rounded border border-white/10 bg-black/40 px-1.5 py-1 text-xs
                         text-zinc-200 outline-none focus:border-accent/60"
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
        <p className="py-4 text-center text-xs italic text-zinc-700">
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
