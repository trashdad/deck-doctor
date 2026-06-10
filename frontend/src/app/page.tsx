"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { DndContext, type DragEndEvent, PointerSensor, useSensor, useSensors } from "@dnd-kit/core";
import { useQuery } from "@tanstack/react-query";
import { SearchPanel } from "@/components/SearchPanel";
import { ZoneColumn } from "@/components/ZoneColumn";
import { StatsSidebar } from "@/components/StatsSidebar";
import { OraclePhrasePanel } from "@/components/OraclePhrasePanel";
import { SemanticFinder } from "@/components/SemanticFinder";
import { RelationshipExplorer } from "@/components/RelationshipExplorer";
import { SuggestionsPanel } from "@/components/SuggestionsPanel";
import { DeckManagerPanel } from "@/components/DeckManagerPanel";
import { ImportExportDialog } from "@/components/ImportExportDialog";
import { DeckCombosPanel } from "@/components/DeckCombosPanel";
import { DeckDoctorPanel } from "@/components/DeckDoctorPanel";
import { SynergyGraph } from "@/components/SynergyGraph";
import { useDeck } from "@/store/deck";
import { useDecksStore } from "@/store/decks";
import { ZONES, type Zone } from "@/lib/zones";
import { analyzeDeck } from "@/lib/api";
import type { DeckEntry } from "@/lib/types";

function HeaderButton({
  onClick,
  disabled,
  title,
  children,
  testid,
}: {
  onClick: () => void;
  disabled?: boolean;
  title: string;
  children: React.ReactNode;
  testid: string;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      data-testid={testid}
      title={title}
      className={[
        "rounded-lg border px-3 py-1.5 text-xs font-semibold tracking-wide transition",
        disabled
          ? "cursor-not-allowed border-zinc-700 text-zinc-600"
          : "border-accent/50 text-accent hover:bg-accent/10",
      ].join(" ")}
    >
      {children}
    </button>
  );
}

export default function Page() {
  const { cards, basics, add, remove, move, setBasic } = useDeck();
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));
  const [suggestOpen, setSuggestOpen] = useState(false);
  const [decksOpen, setDecksOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [combosOpen, setCombosOpen] = useState(false);
  const [doctorOpen, setDoctorOpen] = useState(false);
  const [graphOpen, setGraphOpen] = useState(false);

  const { currentId, saveCurrent } = useDecksStore();

  const deckCards = Object.values(cards);
  const basicEntries = Object.entries(basics);
  const basicCount = basicEntries.reduce((s, [, b]) => s + b.quantity, 0);

  // Stable signature: nonbasic ids + basic id×qty so analysis/save react to both.
  const entries: DeckEntry[] = useMemo(() => {
    const out: DeckEntry[] = deckCards.map((dc) => ({
      id: dc.card.id,
      zone: dc.zone,
      quantity: 1,
    }));
    for (const [id, b] of basicEntries) {
      out.push({ id, zone: "Lands", quantity: b.quantity });
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deckCards, basicEntries.map(([id, b]) => `${id}:${b.quantity}`).join(",")]);

  const commander = deckCards.find((dc) => dc.zone === "Commanders")?.card ?? null;
  const commanderId = commander?.id ?? null;

  const { data: analysis } = useQuery({
    queryKey: ["analyze", entries.map((e) => `${e.id}:${e.quantity}`).sort().join(","), commanderId],
    queryFn: () => analyzeDeck(entries, commanderId),
    enabled: entries.length > 0,
  });

  // Autosave: debounce 2s when a deck is loaded; snapshot to localStorage always.
  const sig = entries.map((e) => `${e.id}:${e.quantity}`).sort().join(",");
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem("simmander.autosave", JSON.stringify(entries));
    }
    if (currentId == null) return;
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => void saveCurrent(), 2000);
    return () => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sig, currentId]);

  function onDragEnd(e: DragEndEvent) {
    const id = String(e.active.id);
    const zone = e.over?.id ? (String(e.over.id) as Zone) : null;
    if (zone && ZONES.includes(zone)) move(id, zone);
  }

  const byZone = (z: Zone) => deckCards.filter((dc) => dc.zone === z);
  const totalCards = deckCards.length + basicCount;

  return (
    <div className="flex h-screen flex-col">
      <OraclePhrasePanel />
      <SemanticFinder />
      <RelationshipExplorer />
      <SuggestionsPanel
        isOpen={suggestOpen}
        onClose={() => setSuggestOpen(false)}
        commander={commander}
        entries={entries}
      />
      <DeckCombosPanel
        isOpen={combosOpen}
        onClose={() => setCombosOpen(false)}
        commander={commander}
        entries={entries}
      />
      <DeckDoctorPanel
        isOpen={doctorOpen}
        onClose={() => setDoctorOpen(false)}
        commander={commander}
        entries={entries}
      />
      <SynergyGraph
        isOpen={graphOpen}
        onClose={() => setGraphOpen(false)}
        commander={commander}
        entries={entries}
      />
      <DeckManagerPanel
        isOpen={decksOpen}
        onClose={() => setDecksOpen(false)}
        onOpenImport={() => {
          setDecksOpen(false);
          setImportOpen(true);
        }}
      />
      <ImportExportDialog isOpen={importOpen} onClose={() => setImportOpen(false)} />

      <header className="flex items-center justify-between border-b border-edge bg-panel px-5 py-3">
        <div className="flex items-baseline gap-3">
          <h1 className="font-display text-xl tracking-wide text-accent">Simmander</h1>
          <span className="text-sm text-zinc-500">Deckbuilder</span>
        </div>
        <div className="flex items-center gap-2">
          <HeaderButton testid="open-decks" title="Saved decks" onClick={() => setDecksOpen(true)}>
            🗂 Decks
          </HeaderButton>
          <HeaderButton
            testid="open-combos"
            title={deckCards.length ? "Combos in / near your deck" : "Add cards first"}
            disabled={deckCards.length === 0}
            onClick={() => setCombosOpen(true)}
          >
            ♾ Combos
          </HeaderButton>
          <HeaderButton
            testid="open-doctor"
            title={commander ? "Deck Doctor" : "Add a commander first"}
            disabled={!commander}
            onClick={() => setDoctorOpen(true)}
          >
            🩺 Doctor
          </HeaderButton>
          <HeaderButton
            testid="open-graph"
            title={totalCards >= 5 ? "Synergy graph" : "Add at least 5 cards"}
            disabled={totalCards < 5}
            onClick={() => setGraphOpen(true)}
          >
            🕸 Graph
          </HeaderButton>
          <HeaderButton
            testid="open-suggestions"
            title={commander ? `Suggestions for ${commander.name}` : "Add a commander first"}
            disabled={!commander}
            onClick={() => setSuggestOpen(true)}
          >
            ⚡ Suggestions
          </HeaderButton>
          <div className="ml-1 text-xs text-zinc-500">{totalCards} cards · simmander.app</div>
        </div>
      </header>

      <DndContext sensors={sensors} onDragEnd={onDragEnd}>
        <div className="flex min-h-0 flex-1">
          <SearchPanel onAdd={add} />

          <main className="grid flex-1 auto-rows-min grid-cols-1 gap-3 overflow-y-auto p-4 scrollbar-thin lg:grid-cols-2 2xl:grid-cols-3">
            {ZONES.map((z) => (
              <ZoneColumn
                key={z}
                zone={z}
                cards={byZone(z)}
                onRemove={remove}
                basics={z === "Lands" ? basics : undefined}
                onSetBasic={z === "Lands" ? setBasic : undefined}
              />
            ))}
          </main>

          <StatsSidebar analysis={analysis ?? null} />
        </div>
      </DndContext>
    </div>
  );
}
