"use client";

import { useEffect, useMemo } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { upgradeSweep } from "@/lib/api";
import { useDeck } from "@/store/deck";
import { useSweepStore } from "@/store/sweep";
import { useRelationshipStore } from "@/store/relationship";
import type { DeckEntry } from "@/lib/types";
import { ReasonChips } from "./SuggestionsPanel";
import { GainBadge } from "./CardUpgradePanel";

export function UpgradeSweepPanel() {
  const { isOpen, efficiency, favorSynergy, close, setEfficiency, toggleSynergy } =
    useSweepStore();
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

  const deckSig = entries.map((e) => e.id).sort().join(",");

  const { data, isFetching, error } = useQuery({
    queryKey: ["sweep", commanderId, deckSig, efficiency, favorSynergy],
    queryFn: () =>
      upgradeSweep(entries, commanderId!, { efficiency, favorSynergy, weak: 16 }),
    enabled: isOpen && commanderId != null,
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });

  if (!isOpen) return null;

  // Drop swaps whose target was already replaced/removed.
  const swaps = (data?.swaps ?? []).filter((s) => cards[s.target.id]);

  return (
    <>
      <div className="fixed inset-0 z-[120] bg-black/40" onClick={close} />

      <div
        className="fixed right-0 top-0 z-[125] flex h-screen w-[460px] flex-col
                   border-l border-accent/30 bg-ink/90 shadow-neon backdrop-blur-md"
        data-testid="sweep-panel"
      >
        {/* Header */}
        <div className="flex items-start justify-between border-b border-accent/30 px-4 py-3">
          <div className="min-w-0">
            <p className="font-display text-[9px] uppercase tracking-wider text-accent">
              Tune-up
            </p>
            <p className="truncate text-sm font-semibold text-accent">
              Weakest cards · better swaps
            </p>
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
              <span className={efficiency <= 0.5 ? "text-accent" : ""}>Keep theme</span>
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
              data-testid="sweep-slider"
            />
          </div>
          <button
            onClick={toggleSynergy}
            className={[
              "w-full rounded border px-2 py-1.5 text-[10px] font-semibold uppercase tracking-wide transition",
              favorSynergy
                ? "border-accent/70 bg-accent/15 text-accent"
                : "border-edge text-zinc-400 hover:border-accent/40 hover:text-accent",
            ].join(" ")}
          >
            ⚡ Favor commander synergy
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto scrollbar-thin">
          {commanderId == null && (
            <p className="px-4 py-10 text-center text-xs text-zinc-500">
              Add a commander to tune up the deck.
            </p>
          )}
          {commanderId != null && isFetching && !data && (
            <div className="flex items-center justify-center py-12">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-accent border-t-transparent" />
            </div>
          )}
          {error != null && (
            <p className="px-4 py-10 text-center text-xs text-red-400">
              Failed to compute the tune-up.
            </p>
          )}
          {data && swaps.length === 0 && !isFetching && (
            <p className="px-4 py-10 text-center text-xs text-zinc-500">
              No weak cards with better replacements found — this deck is tight.
            </p>
          )}

          <ul className="divide-y divide-accent/10">
            {swaps.map((s) => {
              const best = s.options[0];
              return (
                <li key={s.target.id} className="px-3 py-3" data-testid="sweep-swap">
                  {/* Weak card being replaced */}
                  <div className="mb-2 flex items-center gap-2">
                    <button
                      title="Explore relationships"
                      onClick={() => openExplorer(s.target, "similar")}
                      className="h-12 w-9 shrink-0 overflow-hidden rounded border border-red-400/30 bg-zinc-900"
                    >
                      {s.target.image_uris?.normal ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={s.target.image_uris.normal}
                          alt={s.target.name}
                          loading="lazy"
                          className="h-full w-full object-cover opacity-70"
                        />
                      ) : (
                        <span className="block px-0.5 pt-1 text-[7px] leading-tight text-zinc-400">
                          {s.target.name}
                        </span>
                      )}
                    </button>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[11px] font-semibold text-zinc-400 line-through">
                        {s.target.name}
                      </p>
                      <ReasonChips reasons={s.weakness_reasons.slice(0, 2)} />
                    </div>
                    <span className="shrink-0 text-[14px] text-zinc-600">→</span>
                  </div>

                  {/* Replacement options */}
                  <ul className="space-y-1.5 pl-4">
                    {s.options.map((o) => (
                      <li
                        key={o.card.id}
                        className="flex items-center gap-2 rounded border border-accent/10 bg-panel2/40 px-2 py-1.5 transition hover:border-cyan/40"
                      >
                        <button
                          title="Explore"
                          onClick={() => openExplorer(o.card, "similar")}
                          className="h-10 w-7 shrink-0 overflow-hidden rounded border border-accent/30 bg-zinc-900"
                        >
                          {o.card.image_uris?.normal ? (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img
                              src={o.card.image_uris.normal}
                              alt={o.card.name}
                              loading="lazy"
                              className="h-full w-full object-cover"
                            />
                          ) : null}
                        </button>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center justify-between gap-2">
                            <p className="truncate text-[11px] font-semibold text-zinc-200">
                              {o.card.name}
                            </p>
                            <GainBadge gain={o.efficiency_gain} />
                          </div>
                          <ReasonChips reasons={o.reasons.slice(0, 2)} />
                        </div>
                        <button
                          title={`Swap in for ${s.target.name}`}
                          data-testid="sweep-apply"
                          onClick={() => swap(s.target.id, o.card)}
                          className="shrink-0 rounded-full border border-cyan/60 px-2 py-1 text-[9px]
                                     font-bold uppercase tracking-wide text-cyan transition
                                     hover:bg-cyan/15 hover:shadow-neon"
                        >
                          Swap
                        </button>
                      </li>
                    ))}
                  </ul>
                  {best == null && (
                    <p className="pl-4 text-[10px] text-zinc-600">no replacement found</p>
                  )}
                </li>
              );
            })}
          </ul>
        </div>

        {/* Footer */}
        {data && (
          <div className="border-t border-accent/30 px-4 py-2 text-[10px] text-zinc-500">
            {swaps.length} weak cards · cut signal from EDHREC + deck synergy,
            replacements from the upgrade finder
          </div>
        )}
      </div>
    </>
  );
}
