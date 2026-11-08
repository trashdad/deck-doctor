"use client";

import type { Card } from "@/lib/types";
import type { Zone } from "@/lib/zones";
import { MANA_COLORS } from "@/lib/zones";
import { CountPill } from "./CountPill";
import { RoleLedger, type LedgerEntry } from "./RoleLedger";
import { BracketVital } from "./BracketVital";

export interface DeckHeaderProps {
  commander: Card | null;
  count: number;
  target: 100;
  ledger: LedgerEntry[];
  curve: { cmc: number; count: number }[];
  bracket: { floor: number; flags: string[] } | null;
  onOpenCuts: (n: number) => void;
  onOpenComplete: () => void;
  onJumpToLane: (zone: Zone) => void;
  onFlagClick: (flag: string) => void;
  /** Skeleton: the template button is a placeholder until TemplatePanel moves into the rail. */
  templateName?: string;
  onOpenTemplate?: () => void;
  className?: string;
}

/**
 * 8-bin curve sparkline, 22 px high so it fits the ledger row (§4.2 budget: the
 * whole header is ≤ 96 px). Bins ≥ 7 collapse into the last; the bin labels
 * live in the accessible name / title, not as < 11 px text (§3.2).
 */
function CurveSparkline({ curve }: { curve: { cmc: number; count: number }[] }) {
  const bins = new Array(8).fill(0) as number[];
  for (const { cmc, count } of curve) bins[Math.min(7, Math.max(0, Math.round(cmc)))] += count;
  const max = Math.max(1, ...bins);
  const w = 7;
  const gap = 2;
  const h = 22;
  const total = bins.reduce((a, b) => a + b, 0);
  const label = `Mana curve, ${total} cards: ${bins.map((n, i) => `${i === 7 ? "7+" : i} drop ${n}`).join(", ")}`;
  return (
    <svg
      width={bins.length * (w + gap) - gap}
      height={h}
      role="img"
      aria-label={label}
      className="shrink-0"
      data-testid="curve-sparkline"
    >
      <title>{label}</title>
      {bins.map((n, i) => {
        const bh = Math.max(n > 0 ? 2 : 0, Math.round((n / max) * h));
        return (
          <rect key={i} x={i * (w + gap)} y={h - bh} width={w} height={bh} rx={1} fill={i >= 2 && i <= 4 ? "#00eeff" : "#9fd0ff"} opacity={0.9} />
        );
      })}
    </svg>
  );
}

/**
 * Deck at a glance — sticky, two rows, ≤ 96 px at ≥ 1024 px (§4.2):
 *   row 1 (56 px): commander thumb + name/pips · count pill · template · bracket vital
 *   row 2 (22 px): role ledger (one line, scrolls sideways when narrow) · curve sparkline
 * Below 1024 px (§4.9) row 1 may wrap (the bracket drops to its own line) and the
 * ledger strip scrolls horizontally; the template button and sparkline hide.
 */
export function DeckHeader({
  commander,
  count,
  target,
  ledger,
  curve,
  bracket,
  onOpenCuts,
  onOpenComplete,
  onJumpToLane,
  onFlagClick,
  templateName = "Command Zone",
  onOpenTemplate,
  className,
}: DeckHeaderProps) {
  const art = commander?.image_uris?.normal;
  return (
    <header
      data-testid="deck-header"
      className={[
        "sticky top-0 z-rail flex w-full flex-col gap-1 border-b border-edge bg-panel-solid px-3 py-1.5 backdrop-blur-sm",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <div className="flex min-h-14 flex-wrap items-center gap-x-3 gap-y-1 lg:flex-nowrap">
        <div className="flex min-w-0 flex-1 items-center gap-2 lg:max-w-[220px]">
          {commander && art ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={art} alt="" className="h-14 w-10 shrink-0 rounded-[3px] object-cover" />
          ) : (
            <span className="flex h-14 w-10 shrink-0 items-center justify-center rounded-[3px] border border-dashed border-edge text-[11px] text-zinc-500">
              ?
            </span>
          )}
          <div className="min-w-0">
            <p className="truncate text-[13px] font-semibold text-zinc-100">
              {commander ? commander.name : "No commander"}
            </p>
            {commander ? (
              <p className="mt-0.5 flex items-center gap-1">
                {(commander.color_identity.length ? commander.color_identity : ["C"]).map((c) => (
                  <span
                    key={c}
                    className="inline-flex h-4 w-4 items-center justify-center rounded-full text-[11px] font-bold"
                    style={{ background: MANA_COLORS[c] ?? "#444", color: "#0c0a14" }}
                    title={c}
                  >
                    {c}
                  </span>
                ))}
              </p>
            ) : (
              <p className="truncate text-[11px] text-zinc-400">Pick one (left) or paste a list (Import)</p>
            )}
          </div>
        </div>
        <CountPill count={count} target={target} onOpenCuts={onOpenCuts} onOpenComplete={onOpenComplete} />
        <button
          type="button"
          onClick={onOpenTemplate}
          disabled={!onOpenTemplate}
          data-testid="deck-header-template"
          title={`Template: ${templateName} — open options`}
          className="hidden h-9 max-w-[170px] shrink-0 items-center gap-1 rounded border border-edge px-2 text-[13px] text-zinc-300 hover:border-accent/50 hover:text-accent disabled:opacity-60 xl:inline-flex"
        >
          <span className="text-[11px] uppercase tracking-wide text-zinc-500">Template</span>
          <span className="truncate">{templateName}</span>
          <span aria-hidden="true">▾</span>
        </button>
        <BracketVital bracket={bracket} onFlagClick={onFlagClick} compact className="w-full lg:w-auto lg:min-w-0 lg:flex-1" />
      </div>
      <div className="flex items-center gap-x-3">
        <RoleLedger
          ledger={ledger}
          onJumpToLane={onJumpToLane}
          nowrap
          className="min-w-0 flex-1 overflow-x-auto overscroll-x-contain"
          style={{ scrollbarWidth: "none" }}
        />
        <div className="hidden lg:block">
          <CurveSparkline curve={curve} />
        </div>
      </div>
    </header>
  );
}
