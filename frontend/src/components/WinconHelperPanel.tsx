"use client";

import { useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { getRelationships } from "@/lib/api";
import type { Card, RelationshipNeighbor } from "@/lib/types";
import { useDeck } from "@/store/deck";
import { useUI } from "@/store/ui";
import { CardTile } from "./CardTile";

const PER_CARD_LIMIT = 20;
const SHOW_LIMIT = 18;

interface Agg {
  card: Card;
  metric: number;
}

/**
 * Aggregate a relationship axis across many seed cards: for each seed, fetch its
 * neighbours, then dedupe by card id keeping the MAX metric seen. Returns the
 * merged list sorted by metric desc.
 */
function aggregate(results: RelationshipNeighbor[][]): Agg[] {
  const byId = new Map<string, Agg>();
  for (const list of results) {
    for (const n of list) {
      const existing = byId.get(n.card.id);
      if (!existing || n.metric > existing.metric) {
        byId.set(n.card.id, { card: n.card, metric: n.metric });
      }
    }
  }
  return [...byId.values()].sort((a, b) => b.metric - a.metric);
}

/**
 * Win Conditions helper — a fixed right-side panel (mirrors EngineStaplesPanel).
 * Given the win-con cards currently in the Win Conditions zone, shows two grids:
 *   1. "Support your win conditions" — synergy neighbours aggregated across the
 *      win-cons (cards that power up / protect them).
 *   2. "More win conditions like these" — similar neighbours, filtered to only
 *      cards that are themselves win conditions.
 * Both drop cards already in the deck and are de-duped by id.
 */
export function WinconHelperPanel() {
  const open = useUI((s) => s.winconHelperOpen);
  const close = useUI((s) => s.closeWinconHelper);
  const { add, cards: deckCards } = useDeck();

  // The win-con cards currently in the zone — the seeds for both queries.
  const winconSeeds = useMemo(
    () => Object.values(deckCards).filter((dc) => dc.zone === "Win Conditions").map((dc) => dc.card),
    [deckCards],
  );
  const seedIds = winconSeeds.map((c) => c.id).sort().join(",");

  // Escape to close.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [close]);

  const { data: support, isFetching: supportFetching } = useQuery({
    queryKey: ["wincon-support", seedIds],
    queryFn: async () => {
      const lists = await Promise.all(
        winconSeeds.map((c) => getRelationships(c.id, "synergy", PER_CARD_LIMIT)),
      );
      return aggregate(lists);
    },
    enabled: open && winconSeeds.length > 0,
    staleTime: 60_000,
  });

  const { data: more, isFetching: moreFetching } = useQuery({
    queryKey: ["wincon-more", seedIds],
    queryFn: async () => {
      const lists = await Promise.all(
        winconSeeds.map((c) => getRelationships(c.id, "similar", PER_CARD_LIMIT)),
      );
      // Keep only cards that are themselves win conditions.
      return aggregate(lists).filter((a) => a.card.wincon === true);
    },
    enabled: open && winconSeeds.length > 0,
    staleTime: 60_000,
  });

  if (!open) return null;

  // Hide cards already in the deck (incl. the seeds themselves).
  const supportVisible = (support ?? []).filter((a) => !deckCards[a.card.id]).slice(0, SHOW_LIMIT);
  const moreVisible = (more ?? []).filter((a) => !deckCards[a.card.id]).slice(0, SHOW_LIMIT);

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-[120] bg-black/40" onClick={close} />

      {/* Panel */}
      <div
        className="fixed right-0 top-0 z-[125] flex h-screen w-[460px] flex-col
                   border-l border-accent/40 bg-ink/90 shadow-neon backdrop-blur-md"
        data-testid="wincon-helper-panel"
      >
        {/* Header */}
        <div className="flex items-start justify-between border-b border-accent/25 px-4 py-3">
          <div className="min-w-0">
            <p className="font-display text-[9px] uppercase tracking-wider text-accent">Win Conditions</p>
            <p className="mt-1 flex items-center gap-2">
              <span
                className="inline-block bg-contain bg-no-repeat [image-rendering:pixelated]"
                style={{
                  backgroundImage: "url(/deck-doctor/golden-axe.svg)",
                  width: 16,
                  height: 16,
                  filter: "drop-shadow(0 0 6px rgba(255,174,0,.7))",
                }}
              />
              <span className="arcade-bevel truncate text-sm tracking-wide">Build around these</span>
            </p>
            <p className="mt-0.5 text-[10px] text-[#c8b6ff]">
              Recommendations seeded from the{" "}
              <span className="text-cyan">{winconSeeds.length}</span> win condition
              {winconSeeds.length === 1 ? "" : "s"} in your deck.
            </p>
          </div>
          <button
            onClick={close}
            data-testid="wincon-helper-close"
            className="ml-2 mt-0.5 rounded p-1 text-[#9fd0ff] transition hover:bg-accent/15 hover:text-accent"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto scrollbar-thin">
          {/* Section 1 — Support */}
          <Section
            title="Support your win conditions"
            blurb="Cards that power up or protect the win conditions you've chosen."
            fetching={supportFetching && !support}
            items={supportVisible}
            onAdd={add}
          />

          {/* Section 2 — More win conditions */}
          <Section
            title="More win conditions like these"
            blurb="Other ways to close the game that play like yours."
            fetching={moreFetching && !more}
            items={moreVisible}
            onAdd={add}
          />
        </div>
      </div>
    </>
  );
}

function Section({
  title,
  blurb,
  fetching,
  items,
  onAdd,
}: {
  title: string;
  blurb: string;
  fetching: boolean;
  items: Agg[];
  onAdd: (card: Card) => void;
}) {
  return (
    <div className="border-b border-accent/15 px-3 py-3">
      <p className="font-display text-[9px] uppercase tracking-wider text-accent">{title}</p>
      <p className="mb-2 mt-1 text-[10px] text-[#c8b6ff]">{blurb}</p>

      {fetching ? (
        <div className="flex items-center justify-center py-8">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-accent border-t-transparent" />
        </div>
      ) : items.length === 0 ? (
        <p className="py-6 text-center text-xs text-[#9fd0ff]/70">No data yet.</p>
      ) : (
        <div className="grid grid-cols-3 gap-2">
          {items.map((a) => (
            <div key={a.card.id} className="flex flex-col gap-1">
              <CardTile
                card={a.card}
                compact
                badge={a.metric > 0 ? a.metric.toFixed(2) : undefined}
                onAdd={() => onAdd(a.card)}
              />
              <p className="truncate text-center text-[9px] text-[#c8b6ff]" title={a.card.name}>
                {a.card.name}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
