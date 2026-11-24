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

/** The rail body (DoctorRail) carries this id with role="tabpanel". */
export const RAIL_PANEL_ID = "dd-rail-panel";
export const railTabId = (t: RailTab) => `dd-rail-tab-${t}`;

/**
 * WAI-ARIA tabs (review F-14): one Tab stop (the selected tab), ←/→ move and select
 * (automatic activation), Home/End jump; each tab names the panel it controls.
 */
export function RailTabs({ value, onChange, variant = "rail" }: RailTabsProps) {
  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const i = RAIL_TABS.findIndex((t) => t.id === value);
    const n = RAIL_TABS.length;
    const next =
      e.key === "ArrowRight" ? (i + 1) % n
      : e.key === "ArrowLeft" ? (i - 1 + n) % n
      : e.key === "Home" ? 0
      : e.key === "End" ? n - 1
      : -1;
    if (next < 0) return;
    e.preventDefault();
    const id = RAIL_TABS[next].id;
    onChange(id);
    e.currentTarget.querySelector<HTMLElement>(`[data-tab="${id}"]`)?.focus();
  };
  return (
    <div
      role="tablist"
      aria-label="Doctor"
      data-testid={variant === "bar" ? "rail-tabbar" : "rail-tabs"}
      onKeyDown={onKeyDown}
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
            id={railTabId(t.id)}
            aria-selected={active}
            aria-controls={RAIL_PANEL_ID}
            tabIndex={active ? 0 : -1}
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
