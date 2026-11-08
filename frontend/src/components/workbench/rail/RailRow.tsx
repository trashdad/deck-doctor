"use client";

import { useId, useState } from "react";
import type { Card, Reason } from "@/lib/types";
import type { Zone } from "@/lib/zones";
import type { CardContext } from "@/store/ui";
import { ROLE_HUE } from "@/ui/tokens";
import { CardInteractive } from "@/components/card/CardInteractive";
import { ReasonLine } from "@/components/reason/ReasonLine";
import { SourceBadge } from "@/components/reason/SourceBadge";
import { rankReasons, reasonValue } from "@/components/reason/reasonText";

export interface RailRowProps {
  card: Card;
  context: CardContext;
  surfaceId: string;
  /** The lane this card would land in / leave. null → the role was not recognised (chip reads UNKNOWN). */
  role: Zone | null;
  /** e.g. "8/10" or "10 → 9 (below quota)". */
  quotaNote?: string;
  reasons: Reason[];
  commanderName: string | null;
  /** Primary button: "+" (add) or "Cut". */
  primaryLabel: string;
  primaryTitle: string;
  primaryTone?: "primary" | "danger";
  onPrimary: () => void;
  /** Red "⚠ conflicts with X" line, when the backend supplies it. */
  warning?: string;
  /** Row-level note under the sentence (curve note on cuts). */
  note?: string;
  /**
   * Backend sentence to show instead of ReasonLine's template.
   * Chips still come from `reasons`. Omit to keep the ReasonLine sentence.
   */
  sentence?: string;
  /** to_100 row that drops a role below its template quota. */
  breaksQuota?: boolean;
}

/**
 * The shared rail row anatomy (§4.4): thumb · name · role chip · [primary] /
 * reason sentence · chips · why ▾. "?" on the thumb toggles the evidence.
 */
export function RailRow({
  card,
  context,
  surfaceId,
  role,
  quotaNote,
  reasons,
  commanderName,
  primaryLabel,
  primaryTitle,
  primaryTone = "primary",
  onPrimary,
  warning,
  note,
  sentence,
  breaksQuota,
}: RailRowProps) {
  const [why, setWhy] = useState(false);
  const hue = role ? ROLE_HUE[role] : "#a1a1aa";
  return (
    <li
      data-testid="rail-row"
      data-card-id={card.id}
      data-breaks-quota={breaksQuota ? "true" : undefined}
      className={[
        "flex items-start gap-3 border-b border-edge/70 px-3 py-2.5 last:border-b-0",
        breaksQuota ? "border-l-2 border-l-red-400 bg-red-500/10" : "",
      ].join(" ")}
    >
      <CardInteractive
        card={card}
        size="thumb"
        context={context}
        surfaceId={surfaceId}
        primary={onPrimary}
        onWhy={() => setWhy((v) => !v)}
        className="mt-0.5 shrink-0"
        state={{ ierPill: null }}
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-start gap-2">
          <div className="min-w-0 flex-1">
            <p className="truncate text-[13px] font-semibold text-zinc-100">{card.name}</p>
            <p className="mt-0.5 flex flex-wrap items-center gap-1.5">
              <span
                className="inline-flex h-[18px] items-center gap-1 rounded border px-1.5 text-[11px] font-semibold uppercase tracking-wide"
                style={{ borderColor: `${hue}99`, color: hue, background: `${hue}1a` }}
              >
                <span className="h-1.5 w-1.5 rounded-full" style={{ background: hue }} aria-hidden="true" />
                {role ?? "UNKNOWN"}
              </span>
              {quotaNote && <span className="text-[11px] text-zinc-400">{quotaNote}</span>}
            </p>
          </div>
          <button
            type="button"
            title={primaryTitle}
            aria-label={`${primaryTitle}: ${card.name}`}
            onClick={onPrimary}
            className={[
              "flex h-9 min-w-9 shrink-0 items-center justify-center rounded border px-2 text-[13px] font-bold [@media(pointer:coarse)]:h-11 [@media(pointer:coarse)]:min-w-11",
              primaryTone === "danger"
                ? "border-red-400/60 text-red-300 hover:bg-red-500/15"
                : "border-cyan/60 text-cyan hover:bg-cyan/15",
            ].join(" ")}
          >
            {primaryLabel}
          </button>
        </div>
        {sentence !== undefined ? (
          <EvidenceSentence
            sentence={sentence}
            reasons={reasons}
            open={why}
            onToggle={() => setWhy((v) => !v)}
            className="mt-1.5"
          />
        ) : (
          <ReasonLine
            reasons={reasons}
            commanderName={commanderName}
            context={context}
            open={why}
            onOpenChange={setWhy}
            className="mt-1.5"
          />
        )}
        {note && <p className="mt-1 text-[11px] text-zinc-400">{note}</p>}
        {warning && <p className="mt-1 text-[11px] font-semibold text-red-300">⚠ {warning}</p>}
      </div>
    </li>
  );
}

/** ReasonLine's chip row, with a caller-supplied sentence (the backend `reason` string). */
function EvidenceSentence({
  sentence,
  reasons,
  open,
  onToggle,
  className,
}: {
  sentence: string;
  reasons: Reason[];
  open: boolean;
  onToggle: () => void;
  className?: string;
}) {
  const id = useId();
  const ranked = rankReasons(reasons);
  const chips = ranked.slice(0, 2);
  const overflow = ranked.length - chips.length;
  const canExpand = reasons.length > 0;
  return (
    <div data-reason-line className={["min-w-0", className].filter(Boolean).join(" ")}>
      <div className="flex items-start gap-2">
        <p data-reason-sentence className="min-w-0 flex-1 text-[13px] leading-[18px] text-zinc-200">
          {sentence}
        </p>
        {canExpand && (
          <button
            type="button"
            aria-expanded={open}
            aria-controls={id}
            onClick={onToggle}
            className="ml-auto inline-flex h-[18px] shrink-0 items-center gap-0.5 rounded px-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-400 hover:bg-accent/10 hover:text-accent focus-visible:outline focus-visible:outline-1 focus-visible:outline-cyan"
          >
            why <span aria-hidden="true">{open ? "▴" : "▾"}</span>
          </button>
        )}
      </div>
      {chips.length > 0 && (
        <div className="mt-1 flex flex-wrap items-center gap-1.5">
          {chips.map((r, i) => (
            <SourceBadge key={`${r.signal}-${i}`} signal={r.signal} value={reasonValue(r)} title={r.detail} />
          ))}
          {overflow > 0 && (
            <button
              type="button"
              data-reason-overflow
              aria-label={`${overflow} more source${overflow === 1 ? "" : "s"}`}
              aria-expanded={open}
              aria-controls={id}
              onClick={onToggle}
              className="inline-flex h-[18px] items-center rounded border border-edge px-1.5 text-[11px] font-semibold leading-none text-zinc-400 hover:border-accent/60 hover:text-accent"
            >
              +{overflow}
            </button>
          )}
        </div>
      )}
      {canExpand && open && (
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
