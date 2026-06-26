"use client";

import { useEffect, useMemo } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { findCardUpgrades } from "@/lib/api";
import { useDeck } from "@/store/deck";
import { useUpgradeStore } from "@/store/upgrade";
import { useRelationshipStore } from "@/store/relationship";
import type { DeckEntry } from "@/lib/types";
import { ReasonChips } from "./SuggestionsPanel";

function GainBadge({ gain }: { gain: number }) {
  const cls =
    gain > 0.05
      ? "border-green-400/50 bg-green-400/10 text-green-300"
      : gain < -0.05
        ? "border-red-400/50 bg-red-400/10 text-red-300"
        : "border-edge bg-panel2/60 text-zinc-400";
  const sign = gain > 0 ? "+" : "";
  return (
    <span className={`shrink-0 rounded border px-1.5 py-0.5 text-[9px] font-bold ${cls}`}>
      {sign}
      {gain.toFixed(1)} IER
    </span>
  );
}

export function CardUpgradePanel() {
  const {
    isOpen,
    target,
    efficiency,
    favorSynergy,
    favorFlexibility,
    close,
    setEfficiency,
    toggleSynergy,
    toggleFlexibility,
  } = useUpgradeStore();
  const { cards, swap } = useDeck();
  const openExplorer = useRelationshipStore((s) => s.open);

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [close]);

  const deckCards = Object.values(cards);
  const entries: DeckEntry[] = useMemo(
    () => deckCards.map((dc) => ({ id: dc.card.id, zone: dc.zone, quantity: 1 })),
    [deckCards],
  );
  const commanderId =
    deckCards.find((dc) => dc.zone === "Commanders")?.card.id ?? null;

  const { data, isFetching, error } = useQuery({
    queryKey: [
      "upgrade",
      target?.id,
      commanderId,
      efficiency,
      favorSynergy,
      favorFlexibility,
    ],
    queryFn: () =>
      findCardUpgrades(entries, commanderId, target!.id, {
        efficiency,
        favorSynergy,
        favorFlexibility,
        limit: 24,
      }),
    enabled: isOpen && target != null,
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });

  if (!isOpen || !target) return null;

  // Hide options already in the deck (e.g. swapped in moments ago).
  const options = (data?.options ?? []).filter((o) => !cards[o.card.id]);

  return (
    <>
      <div className="fixed inset-0 z-[120] bg-black/40" onClick={close} />

      <div
        className="fixed right-0 top-0 z-[125] flex h-screen w-[460px] flex-col
                   border-l border-accent/30 bg-ink/90 shadow-neon backdrop-blur-md"
        data-testid="upgrade-panel"
      >
        {/* Header */}
        <div className="flex items-start justify-between border-b border-accent/30 px-4 py-3">
          <div className="min-w-0">
            <p className="font-display text-[9px] uppercase tracking-wider text-accent">
              Upgrade · Replace
            </p>
            <p className="truncate text-sm font-semibold text-accent">{target.name}</p>
            {target.ier != null && (
              <span className="mt-1 inline-block rounded border border-accent/40 bg-accent/10 px-1.5 py-0.5 text-[9px] font-bold tracking-wider text-accent">
                IER {target.ier}
              </span>
            )}
          </div>
          <button
            onClick={close}
            className="ml-2 mt-0.5 rounded p-1 text-zinc-500 transition hover:bg-accent/10 hover:text-accent"
          >
            ✕
          </button>
        </div>

        {/* Controls */}
        <div className="space-y-3 border-b border-accent/30 px-4 py-3">
          <div>
            <div className="mb-1 flex justify-between text-[9px] uppercase tracking-wider text-zinc-400">
              <span className={efficiency <= 0.5 ? "text-accent" : ""}>Closest match</span>
              <span className={efficiency > 0.5 ? "text-accent" : ""}>Max efficiency</span>
            </div>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={efficiency}
              onChange={(e) => setEfficiency(parseFloat(e.target.value))}
              className="w-full accent-accent"
              data-testid="upgrade-slider"
            />
          </div>
          <div className="flex gap-2">
            <button
              onClick={toggleSynergy}
              className={[
                "flex-1 rounded border px-2 py-1.5 text-[10px] font-semibold uppercase tracking-wide transition",
                favorSynergy
                  ? "border-accent/70 bg-accent/15 text-accent"
                  : "border-edge text-zinc-400 hover:border-accent/40 hover:text-accent",
              ].join(" ")}
            >
              ⚡ Commander synergy
            </button>
            <button
              onClick={toggleFlexibility}
              className={[
                "flex-1 rounded border px-2 py-1.5 text-[10px] font-semibold uppercase tracking-wide transition",
                favorFlexibility
                  ? "border-cyan/70 bg-cyan/15 text-cyan"
                  : "border-edge text-zinc-400 hover:border-cyan/40 hover:text-cyan",
              ].join(" ")}
            >
              ✦ Multimodal
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto scrollbar-thin">
          {isFetching && !data && (
            <div className="flex items-center justify-center py-12">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-accent border-t-transparent" />
            </div>
          )}

          {error != null && (
            <p className="px-4 py-10 text-center text-xs text-red-400">
              Failed to find upgrades.
            </p>
          )}

          {data && options.length === 0 && !isFetching && (
            <p className="px-4 py-10 text-center text-xs text-zinc-500">
              No similar-but-better replacements found in your colors.
            </p>
          )}

          <ul className="divide-y divide-accent/10">
            {options.map((o) => {
              const art = o.card.image_uris?.normal;
              return (
                <li
                  key={o.card.id}
                  data-testid="upgrade-row"
                  className="flex items-center gap-3 px-3 py-2 transition hover:bg-accent/[0.06] hover:shadow-neon"
                >
                  <button
                    title="Explore relationships"
                    onClick={() => openExplorer(o.card, "similar")}
                    className="h-14 w-10 shrink-0 overflow-hidden rounded border border-accent/30 bg-zinc-900"
                  >
                    {art ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={art}
                        alt={o.card.name}
                        loading="lazy"
                        className="h-full w-full object-cover"
                      />
                    ) : (
                      <span className="block px-0.5 pt-1 text-[7px] leading-tight text-zinc-400">
                        {o.card.name}
                      </span>
                    )}
                  </button>

                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline justify-between gap-2">
                      <p className="truncate text-xs font-semibold text-zinc-200">
                        {o.card.name}
                      </p>
                      <GainBadge gain={o.efficiency_gain} />
                    </div>
                    <div className="mt-0.5 h-1 w-full overflow-hidden rounded bg-panel2/60">
                      <div
                        className="h-full rounded bg-gradient-to-r from-cyan to-magenta"
                        style={{ width: `${Math.min(o.score * 100, 100)}%` }}
                      />
                    </div>
                    <ReasonChips reasons={o.reasons} />
                  </div>

                  <button
                    title={`Swap in for ${target.name}`}
                    data-testid="upgrade-swap"
                    onClick={() => {
                      swap(target.id, o.card);
                      close();
                    }}
                    className="shrink-0 rounded-full border border-cyan/60 px-2.5 py-1.5 text-[10px]
                               font-bold uppercase tracking-wide text-cyan transition
                               hover:bg-cyan/15 hover:shadow-neon"
                  >
                    Swap
                  </button>
                </li>
              );
            })}
          </ul>
        </div>

        {/* Footer */}
        {data && (
          <div className="border-t border-accent/30 px-4 py-2 text-[10px] text-zinc-500">
            {options.length} replacements · same function, ranked by your slider +
            toggles
          </div>
        )}
      </div>
    </>
  );
}
