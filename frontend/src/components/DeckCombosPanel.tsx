"use client";

import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { postDeckCombos } from "@/lib/api";
import { useDeck } from "@/store/deck";
import { useRelationshipStore } from "@/store/relationship";
import { CardTile } from "./CardTile";
import type { Card, DeckEntry, SpellbookCombo } from "@/lib/types";

function ArtThumb({ card, onClick }: { card: Card; onClick: () => void }) {
  const art = card.image_uris?.normal;
  return (
    <button
      title={card.name}
      onClick={onClick}
      className="h-14 w-10 shrink-0 overflow-hidden rounded border border-edge bg-zinc-900"
    >
      {art ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={art} alt={card.name} loading="lazy" className="h-full w-full object-cover" />
      ) : (
        <span className="block px-0.5 pt-1 text-[7px] leading-tight text-zinc-400">
          {card.name}
        </span>
      )}
    </button>
  );
}

function ProducesLine({ combo }: { combo: SpellbookCombo }) {
  if (combo.produces.length === 0) return null;
  return (
    <p className="text-[10px] text-fuchsia-200/90">→ {combo.produces.join(", ")}</p>
  );
}

export function DeckCombosPanel({
  isOpen,
  onClose,
  commander,
  entries,
}: {
  isOpen: boolean;
  onClose: () => void;
  commander: Card | null;
  entries: DeckEntry[];
}) {
  const { add } = useDeck();
  const openExplorer = useRelationshipStore((s) => s.open);

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [onClose]);

  const deckSig = entries.map((e) => e.id).sort().join(",");
  const { data, isFetching } = useQuery({
    queryKey: ["deck-combos", commander?.id ?? null, deckSig],
    queryFn: () => postDeckCombos(entries, commander?.id ?? null),
    enabled: isOpen && entries.length > 0,
    staleTime: 30_000,
  });

  if (!isOpen) return null;

  const complete = data?.complete ?? [];
  const near = data?.near ?? [];

  return (
    <>
      <div className="fixed inset-0 z-[120] bg-black/40" onClick={onClose} />
      <div
        className="fixed right-0 top-0 z-[125] flex h-screen w-[460px] flex-col
                   border-l border-edge bg-panel shadow-2xl"
        data-testid="deck-combos-panel"
      >
        <div className="flex items-start justify-between border-b border-edge px-4 py-3">
          <div>
            <p className="text-[9px] uppercase tracking-widest text-zinc-600">Combos</p>
            <p className="text-sm font-semibold text-accent">In &amp; near your deck</p>
          </div>
          <button
            onClick={onClose}
            className="rounded p-1 text-zinc-500 transition hover:bg-zinc-700 hover:text-zinc-200"
          >
            ✕
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-3 scrollbar-thin">
          {isFetching && !data && (
            <div className="flex items-center justify-center py-12">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-accent border-t-transparent" />
            </div>
          )}

          {/* In your deck */}
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-zinc-500">
            In your deck ({complete.length})
          </p>
          <div data-testid="combos-complete" className="space-y-2">
            {complete.length === 0 && !isFetching && (
              <p className="py-3 text-center text-[11px] text-zinc-600">
                No complete combos yet.
              </p>
            )}
            {complete.map((c) => (
              <div key={c.combo_id} className="rounded-lg border border-edge bg-zinc-900/50 p-2">
                <ProducesLine combo={c} />
                <div className="mt-1 flex flex-wrap gap-1">
                  {c.members.map((m) => (
                    <ArtThumb key={m.id} card={m} onClick={() => openExplorer(m, "synergy")} />
                  ))}
                </div>
              </div>
            ))}
          </div>

          {/* One card away — the killer feature */}
          <p className="mb-2 mt-4 text-[10px] font-semibold uppercase tracking-widest text-zinc-500">
            One card away ({near.length})
          </p>
          <div data-testid="combos-near" className="space-y-2">
            {near.length === 0 && !isFetching && (
              <p className="py-3 text-center text-[11px] text-zinc-600">
                No one-card-away combos.
              </p>
            )}
            {near.map((n) => (
              <div
                key={n.combo.combo_id}
                className="rounded-lg border border-amber-500/50 bg-amber-500/[0.06] p-2"
              >
                <ProducesLine combo={n.combo} />
                <div className="mt-1 flex items-center gap-2">
                  <div className="w-16 shrink-0">
                    <CardTile
                      card={n.missing}
                      compact
                      badge="missing"
                      onAdd={() => add(n.missing)}
                      onClick={() => openExplorer(n.missing, "synergy")}
                    />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs font-semibold text-amber-200">
                      add {n.missing.name}
                    </p>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {n.combo.members
                        .filter((m) => m.id !== n.missing.id)
                        .map((m) => (
                          <span
                            key={m.id}
                            className="rounded bg-white/5 px-1 py-0.5 text-[9px] text-zinc-400"
                          >
                            {m.name}
                          </span>
                        ))}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="border-t border-edge px-4 py-2 text-[10px] text-zinc-500">
          {complete.length} complete · {near.length} one-away · Commander Spellbook
        </div>
      </div>
    </>
  );
}
