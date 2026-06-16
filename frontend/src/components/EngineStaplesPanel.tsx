"use client";

import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { themeSuggest } from "@/lib/api";
import { useDeck } from "@/store/deck";
import { useUI } from "@/store/ui";
import { CardTile } from "./CardTile";

/**
 * Fixed right-side panel showing the most-played cards for the chosen engine theme.
 * Opens via useUI().engineStaples; closes on ✕ or Escape.
 */
export function EngineStaplesPanel() {
  const target = useUI((s) => s.engineStaples);
  const closeEngineStaples = useUI((s) => s.closeEngineStaples);
  const { add, cards: deckCards } = useDeck();

  // Commander id (first commander in deck, if any)
  const commanderCard =
    Object.values(deckCards).find((dc) => dc.zone === "Commanders")?.card ?? null;
  const commanderId = commanderCard?.id ?? null;

  // Escape key handler
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeEngineStaples();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [closeEngineStaples]);

  const { data, isFetching, error } = useQuery({
    queryKey: ["engine-staples", commanderId, target?.themeId],
    queryFn: () =>
      themeSuggest(commanderId!, [target!.themeId], "", 24, 0),
    enabled: target != null && commanderId != null,
    staleTime: 60_000,
  });

  if (!target) return null;

  const engineLabel =
    target.engineKey === "e1"
      ? "Engine 1"
      : target.engineKey === "e2"
        ? "Engine 2"
        : "Engine 3";

  // Hide cards already in the deck
  const visible = (data?.cards ?? []).filter((s) => !deckCards[s.card.id]);

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-[120] bg-black/40"
        onClick={closeEngineStaples}
      />

      {/* Panel */}
      <div
        className="fixed right-0 top-0 z-[125] flex h-screen w-[460px] flex-col
                   border-l border-accent/40 bg-ink/90 shadow-neon backdrop-blur-md"
        data-testid="engine-staples-panel"
      >
        {/* Header */}
        <div className="flex items-start justify-between border-b border-accent/25 px-4 py-3">
          <div className="min-w-0">
            <p className="flex items-center gap-2 font-display text-[9px] uppercase tracking-wider text-accent">
              <span
                className="inline-block bg-contain bg-no-repeat [image-rendering:pixelated]"
                style={{
                  backgroundImage: "url(/deck-doctor/golden-axe.svg)",
                  width: 13,
                  height: 13,
                  filter: "drop-shadow(0 0 3px rgba(255,174,0,.8))",
                }}
              />
              {engineLabel} Staples
            </p>
            <p className="mt-1 truncate text-sm font-semibold text-white [text-shadow:0_0_12px_rgba(255,43,214,0.4)]">
              {target.themeLabel}
            </p>
            <p className="mt-0.5 text-[10px] text-[#c8b6ff]">
              The most-played{" "}
              <span className="text-cyan">{target.themeLabel}</span> cards
              in your colors — tap ＋ to add.
            </p>
          </div>
          <button
            onClick={closeEngineStaples}
            data-testid="engine-staples-close"
            className="ml-2 mt-0.5 rounded p-1 text-[#9fd0ff] transition hover:bg-accent/15 hover:text-accent"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto scrollbar-thin">
          {!commanderId && (
            <p className="px-4 py-10 text-center text-xs text-[#9fd0ff]/70">
              Pick a commander first to see staples for your colors.
            </p>
          )}

          {commanderId && isFetching && !data && (
            <div className="flex items-center justify-center py-12">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-accent border-t-transparent" />
            </div>
          )}

          {commanderId && error != null && (
            <p className="px-4 py-10 text-center text-xs text-red-400">
              Failed to fetch staples.
            </p>
          )}

          {commanderId && data && visible.length === 0 && !isFetching && (
            <p className="px-4 py-10 text-center text-xs text-[#9fd0ff]/70">
              No staples found — all top cards for this theme are already in your deck!
            </p>
          )}

          {/* Card grid */}
          {visible.length > 0 && (
            <div className="grid grid-cols-3 gap-2 p-3">
              {visible.map((s) => (
                <div key={s.card.id} className="flex flex-col gap-1">
                  <CardTile
                    card={s.card}
                    compact
                    badge={s.score > 0 ? s.score.toFixed(2) : undefined}
                    onAdd={() => add(s.card)}
                  />
                  <p
                    className="truncate text-center text-[9px] text-[#c8b6ff]"
                    title={s.card.name}
                  >
                    {s.card.name}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        {data && (
          <div className="border-t border-accent/20 px-4 py-2 text-[10px] text-[#9fd0ff]/80">
            {visible.length} staples shown · theme: {target.themeLabel}
          </div>
        )}
      </div>
    </>
  );
}
