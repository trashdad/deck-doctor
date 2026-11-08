"use client";

import { useId, useState } from "react";
import type { Reason } from "@/lib/types";
import type { CardContext } from "@/store/ui";
import { SourceBadge } from "./SourceBadge";
import { rankReasons, reasonSentence, reasonValue } from "./reasonText";

export interface ReasonLineProps {
  reasons: Reason[];
  commanderName: string | null;
  context: CardContext;
  /** Chips shown inline before a "+N" overflow. Default 2. */
  maxChips?: number;
  /** Default true — show the "why ▾" disclosure. */
  expandable?: boolean;
  /** Controlled disclosure (the row's "?" key / "Why this card?" menu item). */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  className?: string;
}

/**
 * sentence [why ▾] / evidence chips (§5.1).
 * Exactly one [data-reason-sentence]; 0–`maxChips` [data-reason-chip] plus an
 * optional [data-reason-overflow] "+N". "why ▾" sits on the sentence line's right
 * edge so a wrapped chip row never pushes it onto a line of its own.
 */
export function ReasonLine({
  reasons,
  commanderName,
  context,
  maxChips = 2,
  expandable = true,
  open,
  onOpenChange,
  className,
}: ReasonLineProps) {
  const [localOpen, setLocalOpen] = useState(false);
  const isOpen = open ?? localOpen;
  const setOpen = (v: boolean) => {
    setLocalOpen(v);
    onOpenChange?.(v);
  };
  const id = useId();
  const ranked = rankReasons(reasons);
  const lead = ranked[0];
  const chips = ranked.slice(0, maxChips);
  const overflow = ranked.length - chips.length;
  const canExpand = expandable && reasons.length > 0;

  return (
    <div data-reason-line className={["min-w-0", className].filter(Boolean).join(" ")}>
      <div className="flex items-start gap-2">
        <p data-reason-sentence className="min-w-0 flex-1 text-[13px] leading-[18px] text-zinc-200">
          {lead ? reasonSentence(lead, commanderName, context) : "No evidence returned for this card."}
        </p>
        {canExpand && (
          <button
            type="button"
            aria-expanded={isOpen}
            aria-controls={id}
            onClick={() => setOpen(!isOpen)}
            className="ml-auto inline-flex h-[18px] shrink-0 items-center gap-0.5 rounded px-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-400 hover:bg-accent/10 hover:text-accent focus-visible:outline focus-visible:outline-1 focus-visible:outline-cyan"
          >
            why <span aria-hidden="true">{isOpen ? "▴" : "▾"}</span>
          </button>
        )}
      </div>
      {chips.length > 0 && (
        <div className="mt-1 flex flex-wrap items-center gap-1.5">
          {chips.map((r, i) => (
            <SourceBadge key={`${r.signal}-${i}`} signal={r.signal} value={reasonValue(r)} title={r.detail} />
          ))}
          {overflow > 0 &&
            (canExpand ? (
              <button
                type="button"
                data-reason-overflow
                aria-label={`${overflow} more source${overflow === 1 ? "" : "s"}`}
                aria-expanded={isOpen}
                aria-controls={id}
                onClick={() => setOpen(!isOpen)}
                className="inline-flex h-[18px] items-center rounded border border-edge px-1.5 text-[11px] font-semibold leading-none text-zinc-400 hover:border-accent/60 hover:text-accent"
              >
                +{overflow}
              </button>
            ) : (
              <span data-reason-overflow className="inline-flex h-[18px] items-center rounded border border-edge px-1.5 text-[11px] font-semibold leading-none text-zinc-400">
                +{overflow}
              </span>
            ))}
        </div>
      )}
      {expandable && isOpen && (
        <ul id={id} data-reason-evidence className="mt-1.5 space-y-1 border-l border-edge pl-2">
          {ranked.map((r, i) => (
            <li key={`${r.signal}-${i}`} className="flex items-baseline gap-2 text-[11px] leading-[14px] text-zinc-400">
              <SourceBadge signal={r.signal} verbose className="shrink-0" />
              <span className="min-w-0 flex-1 text-zinc-300">{r.detail}</span>
              <span className="shrink-0 font-mono text-zinc-500">{reasonValue(r)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
