"use client";

import { useMemo } from "react";
import { DndContext, type DragEndEvent, PointerSensor, useSensor, useSensors } from "@dnd-kit/core";
import { useQuery } from "@tanstack/react-query";
import { SearchPanel } from "@/components/SearchPanel";
import { ZoneColumn } from "@/components/ZoneColumn";
import { StatsSidebar } from "@/components/StatsSidebar";
import { OraclePhrasePanel } from "@/components/OraclePhrasePanel";
import { SemanticFinder } from "@/components/SemanticFinder";
import { CardLookupPanel } from "@/components/CardLookupPanel";
import { useDeck } from "@/store/deck";
import { ZONES, type Zone } from "@/lib/zones";
import { analyzeDeck } from "@/lib/api";
import type { DeckEntry } from "@/lib/types";

export default function Page() {
  const { cards, add, remove, move } = useDeck();
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));

  const deckCards = Object.values(cards);

  // Stable signature so analysis only refetches when the deck actually changes.
  const entries: DeckEntry[] = useMemo(
    () => deckCards.map((dc) => ({ id: dc.card.id, zone: dc.zone, quantity: 1 })),
    [deckCards],
  );
  const commanderId =
    deckCards.find((dc) => dc.zone === "Commanders")?.card.id ?? null;

  const { data: analysis } = useQuery({
    queryKey: ["analyze", entries.map((e) => e.id).sort().join(","), commanderId],
    queryFn: () => analyzeDeck(entries, commanderId),
    enabled: entries.length > 0,
  });

  function onDragEnd(e: DragEndEvent) {
    const id = String(e.active.id);
    const zone = e.over?.id ? (String(e.over.id) as Zone) : null;
    if (zone && ZONES.includes(zone)) move(id, zone);
  }

  const byZone = (z: Zone) => deckCards.filter((dc) => dc.zone === z);

  return (
    <div className="flex h-screen flex-col">
      <OraclePhrasePanel />
      <SemanticFinder />
      <CardLookupPanel />
      <header className="flex items-center justify-between border-b border-edge bg-panel px-5 py-3">
        <div className="flex items-baseline gap-3">
          <h1 className="font-display text-xl tracking-wide text-accent">Simmander</h1>
          <span className="text-sm text-zinc-500">Deckbuilder</span>
        </div>
        <div className="text-xs text-zinc-500">
          {deckCards.length} cards · simmander.app
        </div>
      </header>

      <DndContext sensors={sensors} onDragEnd={onDragEnd}>
        <div className="flex min-h-0 flex-1">
          <SearchPanel onAdd={add} />

          <main className="grid flex-1 auto-rows-min grid-cols-1 gap-3 overflow-y-auto p-4 scrollbar-thin lg:grid-cols-2 2xl:grid-cols-3">
            {ZONES.map((z) => (
              <ZoneColumn key={z} zone={z} cards={byZone(z)} onRemove={remove} />
            ))}
          </main>

          <StatsSidebar analysis={analysis ?? null} />
        </div>
      </DndContext>
    </div>
  );
}
