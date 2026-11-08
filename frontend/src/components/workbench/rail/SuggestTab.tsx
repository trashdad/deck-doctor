"use client";

import { useState } from "react";
import type { Card, Suggestion, SuggestionResponse } from "@/lib/types";
import { matchingZones } from "@/lib/functions";
import { CardSurface } from "@/components/card/CardSurface";
import { RailRow } from "./RailRow";

export interface SuggestTabProps {
  commander: Card | null;
  tier: SuggestionResponse["tier"] | null;
  suggestions: Suggestion[];
  onAdd: (card: Card) => void;
  /** Skeleton: set when the query is in flight. */
  loading?: boolean;
}

const TIER_COPY: Record<SuggestionResponse["tier"], string> = {
  edhrec: "EDHREC · real decks · mechanics · combos",
  cooccurrence: "real decks · mechanics · combos (no EDHREC page for this commander)",
  color_staple: "generic staples in your colors",
};

/** Suggest tab (§4.4): source line in words, filter row, rows with reasons as sentences. */
export function SuggestTab({ commander, tier, suggestions, onAdd, loading }: SuggestTabProps) {
  const [hideStaples, setHideStaples] = useState(true);
  const rows = hideStaples
    ? suggestions.filter((s) => !(s.reasons.length > 0 && s.reasons.every((r) => r.signal === "staple")))
    : suggestions;

  if (!commander) {
    return (
      <EmptyState testid="suggest-panel">
        No commander → <strong>Pick one</strong> (left) or <strong>paste a list</strong> (Import).
      </EmptyState>
    );
  }

  return (
    <section data-testid="suggest-panel" aria-label="Suggestions" className="flex min-h-0 flex-1 flex-col">
      <div className="border-b border-edge px-3 py-2">
        <p className="text-[11px] uppercase tracking-wide text-zinc-400">
          Source: <span className="normal-case tracking-normal text-zinc-200">{tier ? TIER_COPY[tier] : "UNKNOWN"}</span>
        </p>
        {tier === "color_staple" && (
          <p className="mt-1 text-[11px] text-amber-300">
            Little deck-specific data for this commander — these are generic staples in your colors.
          </p>
        )}
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <label className="inline-flex h-7 cursor-pointer items-center gap-1.5 rounded border border-edge px-2 text-[11px] font-semibold text-zinc-300 has-[:checked]:border-accent/60 has-[:checked]:text-accent">
            <input type="checkbox" checked={hideStaples} onChange={(e) => setHideStaples(e.target.checked)} className="accent-[#ffd24a]" />
            Hide staples
          </label>
          <button
            type="button"
            disabled
            title="Budget filter applies once the backend accepts it (today: lands only)"
            className="inline-flex h-7 items-center gap-1 rounded border border-edge px-2 text-[11px] font-semibold text-zinc-400 disabled:opacity-60"
          >
            Budget: any ▾
          </button>
        </div>
      </div>
      {loading && rows.length === 0 ? (
        <p className="px-3 py-4 text-[13px] text-zinc-400">Looking at this deck…</p>
      ) : rows.length === 0 ? (
        <EmptyState>
          Nothing left to suggest{hideStaples ? " — untick Hide staples to see generic picks" : ""}. Try <strong>Tune-up</strong>.
        </EmptyState>
      ) : (
        <CardSurface id="rail-suggest" orientation="column" label="Suggested cards" className="min-h-0 flex-1 overflow-y-auto">
          <ul>
            {rows.map((s) => (
              <RailRow
                key={s.card.id}
                card={s.card}
                context="suggest"
                surfaceId="rail-suggest"
                role={s.card.wincon ? "Win Conditions" : matchingZones(s.card)[0]}
                reasons={s.reasons}
                commanderName={commander.name}
                primaryLabel="+"
                primaryTitle="Add to deck"
                onPrimary={() => onAdd(s.card)}
              />
            ))}
          </ul>
        </CardSurface>
      )}
    </section>
  );
}

export function EmptyState({ children, testid }: { children: React.ReactNode; testid?: string }) {
  return (
    <div data-testid={testid} className="px-4 py-6 text-center text-[13px] leading-[18px] text-zinc-300">
      {children}
    </div>
  );
}
