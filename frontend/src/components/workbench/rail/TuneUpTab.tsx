"use client";

import type { Card, UpgradeSweepResponse } from "@/lib/types";
import { ReasonChips } from "@/components/SuggestionsPanel";
import { GainBadge } from "@/components/CardUpgradePanel";
import { EmptyState } from "./SuggestTab";

export interface TuneUpTabProps {
  hasCommander: boolean;
  /** `/deck/upgrade-sweep` response (same endpoint UpgradeSweepPanel uses); undefined = not fetched. */
  data?: UpgradeSweepResponse;
  loading?: boolean;
  error?: boolean;
  onSwap?: (targetId: string, replacement: Card) => void;
  onOpenCard?: (card: Card) => void;
}

/** Tune-up tab — UpgradeSweepPanel's body (weakest cards + same-role swaps), fed by the caller's query (§4.6). */
export function TuneUpTab({ hasCommander, data, loading, error, onSwap, onOpenCard }: TuneUpTabProps) {
  if (!data) {
    return (
      <EmptyState testid="tuneup-panel">
        {!hasCommander ? (
          <>
            No commander → <strong>Pick one</strong> (left) or <strong>paste a list</strong> (Import).
          </>
        ) : error ? (
          <>Failed to compute the tune-up.</>
        ) : loading ? (
          <>Finding your weakest cards…</>
        ) : (
          <>
            Tune-up finds your weakest cards and a same-role swap for each. <strong>Run Tune-up</strong> to start.
          </>
        )}
      </EmptyState>
    );
  }
  const swaps = data.swaps ?? [];
  return (
    <div data-testid="tuneup-panel" className="flex min-h-0 flex-1 flex-col overflow-y-auto scrollbar-thin">
      {swaps.length === 0 && !loading && (
        <p className="px-4 py-10 text-center text-xs text-zinc-500">
          No weak cards with better replacements found — this deck is tight.
        </p>
      )}
      <ul className="divide-y divide-accent/10">
        {swaps.map((s) => (
          <li key={s.target.id} className="px-3 py-3" data-testid="sweep-swap">
            <div className="mb-2 flex items-center gap-2">
              <button
                type="button"
                title="Explore relationships"
                onClick={onOpenCard ? () => onOpenCard(s.target) : undefined}
                className="h-12 w-9 shrink-0 overflow-hidden rounded border border-red-400/30 bg-zinc-900"
              >
                {s.target.image_uris?.normal ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={s.target.image_uris.normal} alt={s.target.name} loading="lazy" className="h-full w-full object-cover opacity-70" />
                ) : (
                  <span className="block px-0.5 pt-1 text-[7px] leading-tight text-zinc-400">{s.target.name}</span>
                )}
              </button>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[11px] font-semibold text-zinc-400 line-through">{s.target.name}</p>
                <ReasonChips reasons={s.weakness_reasons.slice(0, 2)} />
              </div>
              <span className="shrink-0 text-[14px] text-zinc-600">→</span>
            </div>
            <ul className="space-y-1.5 pl-4">
              {s.options.map((o) => (
                <li
                  key={o.card.id}
                  className="flex items-center gap-2 rounded border border-accent/10 bg-panel2/40 px-2 py-1.5 transition hover:border-cyan/40"
                >
                  <button
                    type="button"
                    title="Explore"
                    onClick={onOpenCard ? () => onOpenCard(o.card) : undefined}
                    className="h-10 w-7 shrink-0 overflow-hidden rounded border border-accent/30 bg-zinc-900"
                  >
                    {o.card.image_uris?.normal ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={o.card.image_uris.normal} alt={o.card.name} loading="lazy" className="h-full w-full object-cover" />
                    ) : null}
                  </button>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <p className="truncate text-[11px] font-semibold text-zinc-200">{o.card.name}</p>
                      <GainBadge gain={o.efficiency_gain} />
                    </div>
                    <ReasonChips reasons={o.reasons.slice(0, 2)} />
                  </div>
                  {onSwap && (
                    <button
                      type="button"
                      title={`Swap in for ${s.target.name}`}
                      data-testid="sweep-apply"
                      onClick={() => onSwap(s.target.id, o.card)}
                      className="shrink-0 rounded-full border border-cyan/60 px-2 py-1 text-[9px] font-bold uppercase tracking-wide text-cyan transition hover:bg-cyan/15 hover:shadow-neon"
                    >
                      Swap
                    </button>
                  )}
                </li>
              ))}
            </ul>
            {s.options.length === 0 && <p className="pl-4 text-[10px] text-zinc-600">no replacement found</p>}
          </li>
        ))}
      </ul>
      <p className="px-4 py-2 text-[10px] text-zinc-500">
        {swaps.length} weak cards · cut signal from EDHREC + deck synergy, replacements from the upgrade finder
      </p>
    </div>
  );
}
