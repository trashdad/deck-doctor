"use client";

import type { RailTab } from "@/store/ui";

export const RAIL_TABS: { id: RailTab; label: string; key: string }[] = [
  { id: "suggest", label: "Suggest", key: "1" },
  { id: "cuts", label: "Cuts", key: "2" },
  { id: "tuneup", label: "Tune-up", key: "3" },
  { id: "combos", label: "Combos", key: "4" },
  { id: "pivot", label: "Pivot", key: "5" },
];

export interface RailTabsProps {
  value: RailTab;
  onChange: (t: RailTab) => void;
  /** "rail" (desktop right rail) or "bar" (mobile bottom tab bar, 56 px). */
  variant?: "rail" | "bar";
}

export function RailTabs({ value, onChange, variant = "rail" }: RailTabsProps) {
  return (
    <div
      role="tablist"
      aria-label="Doctor"
      data-testid={variant === "bar" ? "rail-tabbar" : "rail-tabs"}
      className={
        variant === "bar"
          ? "flex h-14 items-stretch border-t border-edge bg-panel-solid"
          : "flex items-stretch border-b border-edge"
      }
    >
      {RAIL_TABS.map((t) => {
        const active = t.id === value;
        return (
          <button
            key={t.id}
            role="tab"
            type="button"
            aria-selected={active}
            data-tab={t.id}
            onClick={() => onChange(t.id)}
            className={[
              "relative flex min-h-11 flex-1 items-center justify-center px-1 text-[13px] font-semibold tracking-wide transition-colors",
              active ? "text-accent" : "text-zinc-400 hover:text-zinc-100",
            ].join(" ")}
          >
            {t.label}
            {active && (
              <span
                aria-hidden="true"
                className={`absolute inset-x-2 h-0.5 bg-gradient-to-r from-magenta to-accent ${variant === "bar" ? "top-0" : "bottom-0"}`}
              />
            )}
          </button>
        );
      })}
    </div>
  );
}
