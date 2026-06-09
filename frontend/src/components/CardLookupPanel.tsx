"use client";

import { useEffect, useRef } from "react";
import { useCardLookupStore } from "@/store/cardLookup";
import { useDeck } from "@/store/deck";
import { CardTile } from "./CardTile";

export function CardLookupPanel() {
  const { isOpen, mode, sourceCard, results, loading, close } =
    useCardLookupStore();
  const { add } = useDeck();
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [close]);

  if (!isOpen) return null;

  const title =
    mode === "similar"
      ? `SIMILAR TO: ${sourceCard?.name ?? ""}`
      : `BEST COMBOS FOR: ${sourceCard?.name ?? ""}`;

  const subtitle =
    mode === "similar"
      ? "Cards with the most overlapping semantic abilities (TF-IDF cosine)"
      : "Cards whose abilities most complement this one";

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-[140] bg-black/40 backdrop-blur-[1px]"
        onClick={close}
      />

      {/* Panel */}
      <div
        ref={ref}
        className="fixed right-0 top-0 z-[145] flex h-screen w-[440px] flex-col
                   border-l border-edge bg-panel shadow-2xl"
      >
        {/* Header */}
        <div className="flex items-start justify-between border-b border-edge px-4 py-3">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-widest text-accent">
              {title}
            </p>
            <p className="mt-0.5 text-[10px] text-zinc-500">{subtitle}</p>
          </div>
          <button
            onClick={close}
            className="ml-2 mt-0.5 rounded p-1 text-zinc-500 transition hover:bg-zinc-700 hover:text-zinc-200"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-3 scrollbar-thin">
          {loading && (
            <div className="flex items-center justify-center py-12">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-accent border-t-transparent" />
            </div>
          )}

          {!loading && results?.length === 0 && (
            <p className="py-8 text-center text-xs text-zinc-500">
              No results — card may not have semantic tags yet.
            </p>
          )}

          {!loading && results && results.length > 0 && (
            <div className="grid grid-cols-3 gap-2">
              {results.map((card) => (
                <CardTile
                  key={card.id}
                  card={card}
                  compact
                  onClick={() => {
                    add(card);
                  }}
                />
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        {!loading && results && results.length > 0 && (
          <div className="border-t border-edge px-4 py-2 text-[10px] text-zinc-500">
            {results.length} cards · click to add to deck
          </div>
        )}
      </div>
    </>
  );
}
