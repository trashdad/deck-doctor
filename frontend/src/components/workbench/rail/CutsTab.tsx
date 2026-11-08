"use client";

import { useEffect, useState } from "react";
import type { Card } from "@/lib/types";
import { matchingZones } from "@/lib/functions";
import { CardSurface } from "@/components/card/CardSurface";
import { type CutRow, cutQuotaNote, cutReasonSentence, cutReasons, cutRoleZone } from "@/lib/cuts";
import { RailRow } from "./RailRow";
import { EmptyState } from "./SuggestTab";

export interface CutsTabProps {
  commander: Card | null;
  count: number;
  /** How many cards to cut (backend `target`), not the deck size. */
  target: number;
  onTargetChange: (n: number) => void;
  candidates: CutRow[];
  onCut: (card: Card) => void;
  /** One undo step for every card. Falls back to per-row `onCut` when omitted. */
  onCutAll?: (cards: Card[]) => void;
  /** From the to_100 response. undefined = not loaded yet (omit). null = field missing (UNKNOWN). */
  overBy?: number | null;
  shortfall?: number | null;
  loading?: boolean;
  error?: boolean;
}

/** Cuts tab (§4.5): to_100 rows, quota warning, cut-all. */
export function CutsTab({
  commander,
  count,
  target,
  onTargetChange,
  candidates,
  onCut,
  onCutAll,
  overBy,
  shortfall,
  loading,
  error,
}: CutsTabProps) {
  // Typed text, so the field can be emptied and retyped; the clamped value is committed only when valid.
  const [draft, setDraft] = useState(String(target));
  useEffect(() => setDraft(String(target)), [target]);

  if (!commander) {
    return (
      <EmptyState testid="cuts-panel">
        No commander → <strong>Pick one</strong> (left) or <strong>paste a list</strong> (Import).
      </EmptyState>
    );
  }
  if (count <= 100 && candidates.length === 0) {
    return (
      <EmptyState testid="cuts-panel">
        Deck at {count} → Nothing to cut; try <strong>Tune-up</strong>.
      </EmptyState>
    );
  }

  // Rows that would drop a role below quota stay listed, but Cut all skips them (§4.5).
  const safe = candidates.filter((c) => c.breaks_quota !== true);
  const batch = safe.slice(0, Math.max(0, target));

  return (
    <section data-testid="cuts-panel" aria-label="Cuts" className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5 border-b border-edge px-3 py-2">
        {overBy !== undefined && (
          <span data-testid="cuts-over-by" className="text-[13px] font-semibold tabular-nums text-accent">
            {typeof overBy === "number" ? `${overBy} over` : "over by UNKNOWN"}
          </span>
        )}
        <label className="flex items-center gap-1.5 text-[13px] text-zinc-200">
          target
          <input
            type="number"
            min={1}
            max={30}
            value={draft}
            data-testid="cuts-target"
            onChange={(e) => {
              setDraft(e.target.value);
              const n = Number(e.target.value);
              if (e.target.value.trim() !== "" && Number.isFinite(n) && n >= 1) onTargetChange(n);
            }}
            onBlur={() => setDraft(String(target))}
            className="h-8 w-14 rounded border border-edge bg-ink/60 px-2 text-center text-[13px] text-zinc-100"
          />
        </label>
        <span className="text-[11px] text-zinc-400">(deck is {count})</span>
        <button
          type="button"
          data-testid="cuts-all"
          disabled={batch.length === 0}
          title={
            batch.length === 0
              ? "No cut that stays at or above quota"
              : `Cut ${batch.length} card${batch.length === 1 ? "" : "s"} that stay at or above quota`
          }
          onClick={() => {
            const cards = batch.map((c) => c.card);
            if (onCutAll) onCutAll(cards);
            else cards.forEach(onCut);
          }}
          className="ml-auto h-8 rounded border border-accent/50 px-2 text-[13px] font-semibold text-accent hover:bg-accent/10 disabled:opacity-50"
        >
          {batch.length > 0 ? `Cut all ${batch.length}` : "Cut all"}
        </button>
      </div>
      {shortfall !== undefined && (shortfall === null || shortfall > 0) && (
        <p
          data-testid="cuts-shortfall"
          className="border-b border-edge px-3 py-2 text-[13px] leading-[18px] text-amber-200"
        >
          {typeof shortfall === "number"
            ? `Shortfall ${shortfall}: fewer legal cuts than the target.`
            : "Shortfall UNKNOWN"}
        </p>
      )}
      {error && candidates.length === 0 ? (
        <EmptyState>The cuts request failed.</EmptyState>
      ) : loading && candidates.length === 0 ? (
        <p className="px-3 py-4 text-[13px] text-zinc-400">Ranking cuts…</p>
      ) : candidates.length === 0 ? (
        <EmptyState>No cuts returned.</EmptyState>
      ) : (
        <CardSurface id="rail-cuts" orientation="column" label="Cut candidates" className="min-h-0 flex-1 overflow-y-auto">
          <ul>
            {candidates.map((c, idx) => {
              const breaks = c.breaks_quota === true;
              const sentence = cutReasonSentence(c);
              const zone = cutRoleZone(c.role);
              const role = zone === undefined ? (c.card.wincon ? "Win Conditions" : matchingZones(c.card)[0]) : zone;
              return (
                <RailRow
                  // One row per card copy: cutting 4 Forests returns 4 rows with the same card id.
                  key={`${c.card.id}-${idx}`}
                  card={c.card}
                  context="cut"
                  surfaceId="rail-cuts"
                  role={role}
                  quotaNote={cutQuotaNote(c)}
                  reasons={cutReasons(c)}
                  commanderName={commander.name}
                  primaryLabel={breaks ? "Cut anyway" : "Cut"}
                  primaryTitle={breaks ? "Cut anyway — drops a role below quota" : "Cut from deck"}
                  primaryTone="danger"
                  onPrimary={() => onCut(c.card)}
                  sentence={sentence}
                  note={sentence ? undefined : `cmc ${c.card.cmc}`}
                  breaksQuota={breaks}
                  warning={breaks ? "Below quota" : undefined}
                />
              );
            })}
          </ul>
        </CardSurface>
      )}
    </section>
  );
}
