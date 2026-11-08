"use client";

import { sourceInfo } from "./reasonText";

export interface SourceBadgeProps {
  signal: string;
  /** Optional evidence number shown after the label, e.g. "0.69". */
  value?: string;
  title?: string;
  /** Evidence list: name unknown signals by their raw backend id instead of "OTHER". */
  verbose?: boolean;
  className?: string;
}

/**
 * 11 px source chip. One muted style for every source (§3.4: hue encodes nothing
 * here, so no hue); the label + number carry the meaning. `data-signal` keeps the
 * raw id for tests and styling hooks.
 */
export function SourceBadge({ signal, value, title, verbose, className }: SourceBadgeProps) {
  const info = sourceInfo(signal);
  const label = verbose && !info.known ? signal.toUpperCase().replace(/_/g, " ") : info.label;
  return (
    <span
      data-reason-chip
      data-signal={signal}
      title={title}
      className={[
        "inline-flex h-[18px] items-center gap-1 rounded border border-edge px-1.5 text-[11px] font-semibold leading-none tracking-wide text-zinc-400",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {label}
      {value && <span className="font-mono font-normal text-zinc-300">{value}</span>}
    </span>
  );
}
