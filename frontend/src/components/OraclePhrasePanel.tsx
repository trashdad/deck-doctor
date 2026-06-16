"use client";

import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useOracle } from "@/store/oracle";
import { useDeck } from "@/store/deck";
import { searchByOracleText } from "@/lib/api";
import { CardTile } from "./CardTile";
import type { Card } from "@/lib/types";

export function OraclePhrasePanel() {
  const { phraseVariants, selectedPattern, selectPattern, closePhrase } = useOracle((s) => ({
    phraseVariants: s.phraseVariants,
    selectedPattern: s.selectedPattern,
    selectPattern: s.selectPattern,
    closePhrase: s.closePhrase,
  }));
  const addCard = useDeck((s) => s.add);

  // Auto-select the first variant whenever the panel opens with new variants
  useEffect(() => {
    if (phraseVariants && phraseVariants.length > 0 && !selectedPattern) {
      selectPattern(phraseVariants[0].pattern);
    }
  }, [phraseVariants, selectedPattern, selectPattern]);

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["oracle-phrase", selectedPattern],
    queryFn: () => searchByOracleText(selectedPattern!),
    enabled: !!selectedPattern && selectedPattern.length >= 4,
    staleTime: 60_000,
  });

  if (!phraseVariants) return null;

  const handleAdd = (card: Card) => {
    addCard(card);
  };

  return (
    <>
      {/* Backdrop — click to close */}
      <div
        className="fixed inset-0 z-[90] bg-black/30 backdrop-blur-[1px]"
        onClick={closePhrase}
      />

      {/* Drawer */}
      <aside
        className="fixed right-0 top-0 z-[100] flex h-screen w-96 flex-col
                   border-l border-accent/30 bg-ink/90 shadow-neon backdrop-blur-md"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-accent/30 px-4 py-3">
          <div>
            <h2 className="arcade-bevel text-sm">Find similar cards</h2>
            <p className="text-[10px] text-zinc-500">Select a phrase pattern below</p>
          </div>
          <button
            onClick={closePhrase}
            className="flex h-7 w-7 items-center justify-center rounded text-zinc-400
                       transition hover:bg-accent/10 hover:text-accent"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        {/* Phrase options */}
        <div className="border-b border-accent/30 p-3">
          <div className="space-y-1">
            {phraseVariants.map((v, i) => (
              <button
                key={i}
                onClick={() => selectPattern(v.pattern)}
                className={[
                  "w-full rounded px-3 py-2 text-left text-xs leading-snug transition-colors",
                  selectedPattern === v.pattern
                    ? "bg-accent/20 text-accent ring-1 ring-accent/40"
                    : "text-zinc-300 hover:bg-accent/10",
                ].join(" ")}
              >
                {v.label}
              </button>
            ))}
          </div>
        </div>

        {/* Results header */}
        <div className="flex items-center justify-between px-4 py-2">
          <span className="text-[10px] text-zinc-500">
            {isFetching
              ? "Searching…"
              : data
              ? `${data.length} card${data.length !== 1 ? "s" : ""} match`
              : ""}
          </span>
          {data && data.length > 0 && (
            <span className="text-[10px] text-zinc-600">Click to add to deck</span>
          )}
        </div>

        {/* Card grid */}
        <div className="grid grid-cols-2 gap-2 overflow-y-auto p-3 scrollbar-thin">
          {isLoading && (
            <p className="col-span-2 py-4 text-center text-xs text-zinc-500">Searching…</p>
          )}
          {!isLoading && data?.length === 0 && (
            <p className="col-span-2 py-4 text-center text-xs text-zinc-600">No matches found.</p>
          )}
          {data?.map((card) => (
            <CardTile
              key={card.id}
              card={card}
              compact
              onClick={() => handleAdd(card)}
            />
          ))}
        </div>
      </aside>
    </>
  );
}
