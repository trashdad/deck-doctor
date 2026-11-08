"use client";

import type { CSSProperties } from "react";
import type { Zone } from "@/lib/zones";
import { ROLE_HUE } from "@/ui/tokens";

export interface LedgerEntry {
  zone: Zone;
  have: number;
  /** null = no template quota for this role. */
  quota: number | null;
}

export interface RoleLedgerProps {
  ledger: LedgerEntry[];
  onJumpToLane?: (zone: Zone) => void;
  /** One line that scrolls sideways (deck header row 2) instead of wrapping. */
  nowrap?: boolean;
  className?: string;
  style?: CSSProperties;
}

/**
 * One segment per template role: `label n/quota` + a 6 px bar in the role hue
 * (red tint below quota, gold above). Color is never the only channel (§3.4).
 */
export function RoleLedger({ ledger, onJumpToLane, nowrap, className, style }: RoleLedgerProps) {
  return (
    <div
      data-testid="role-ledger"
      className={["flex gap-x-3 gap-y-1", nowrap ? "flex-nowrap" : "flex-wrap", className].filter(Boolean).join(" ")}
      style={style}
    >
      {ledger.map(({ zone, have, quota }) => {
        const status = quota === null ? "none" : have < quota ? "under" : have > quota ? "over" : "at";
        const hue = ROLE_HUE[zone];
        const pct = quota ? Math.min(100, Math.round((have / quota) * 100)) : 100;
        return (
          <button
            key={zone}
            type="button"
            data-zone={zone}
            data-status={status}
            onClick={onJumpToLane ? () => onJumpToLane(zone) : undefined}
            className="group flex min-w-[72px] shrink-0 flex-col gap-0.5 rounded px-1 text-left hover:bg-accent/10 focus-visible:outline focus-visible:outline-1 focus-visible:outline-cyan"
            title={quota === null ? `${zone}: ${have}` : `${zone}: ${have} of ${quota}`}
          >
            <span className="flex items-baseline justify-between gap-2 leading-[14px]">
              <span className="whitespace-nowrap text-[11px] font-semibold uppercase tracking-wide text-zinc-400 group-hover:text-zinc-200">
                {zone}
              </span>
              <span
                className={`text-[13px] font-semibold tabular-nums ${
                  status === "under" ? "text-red-300" : status === "over" ? "text-accent" : "text-zinc-100"
                }`}
              >
                {have}
                {quota !== null && <span className="text-zinc-500">/{quota}</span>}
              </span>
            </span>
            <span className="relative block h-[6px] w-full overflow-hidden rounded-sm bg-black/40">
              <span
                className="absolute inset-y-0 left-0 rounded-sm"
                style={{
                  width: `${pct}%`,
                  background: status === "under" ? "#ef4444" : status === "over" ? "#ffd24a" : hue,
                  opacity: status === "under" ? 0.8 : 1,
                }}
              />
            </span>
          </button>
        );
      })}
    </div>
  );
}
