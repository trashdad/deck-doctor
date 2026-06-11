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
import { TemplatePanel } from "@/components/TemplatePanel";
import { UserMenu } from "@/components/UserMenu";
import { useDeck } from "@/store/deck";
import { useDecksStore } from "@/store/decks";
import { useTemplateStore } from "@/store/template";
import { useAuth } from "@/store/auth";
import { ZONES, type Zone } from "@/lib/zones";
import { analyzeDeck, getTemplates, saveDeck } from "@/lib/api";
import type { DeckEntry } from "@/lib/types";

function TemplateMenu() {
  const { templates, selectedId, select } = useTemplateStore();
  const [open, setOpen] = useState(false);
  const current = templates.find((t) => t.id === selectedId);
  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        data-testid="template-menu"
        title="Composition template (sets the Deck Doctor quotas)"
        className="rounded-lg border border-accent/50 px-3 py-1.5 text-xs font-semibold tracking-wide
                   text-accent transition hover:bg-accent/10"
      >
        ⚜ {current?.name ?? "Template"} ▾
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-[130]" onClick={() => setOpen(false)} />
          <div className="absolute right-0 z-[131] mt-1 w-64 rounded-lg border border-edge bg-panel p-1 shadow-2xl">
            {templates.map((t) => (
              <button
                key={t.id}
                data-testid={`template-opt-${t.id}`}
                onClick={() => {
                  select(t.id);
                  setOpen(false);
                }}
                className={[
                  "flex w-full flex-col rounded-md px-3 py-2 text-left transition",
                  t.id === selectedId ? "bg-accent/15" : "hover:bg-white/5",
                ].join(" ")}
              >
                <span className="flex items-center justify-between gap-2 text-xs font-semibold text-zinc-200">
                  {t.name}
                  <span className="shrink-0 text-[8px] uppercase tracking-widest text-zinc-500">
                    {t.source}
                  </span>
                </span>
                <span className="text-[10px] tracking-wide text-zinc-500">
                  {t.counts.land}/{t.counts.ramp}/{t.counts.card_draw}/
                  {t.counts.removal}/{t.counts.board_wipe} · land/ramp/draw/rmv/wipe
                </span>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

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

  // Template catalog → store (drives the header dropdown + Doctor quotas).
  const setCatalog = useTemplateStore((s) => s.setCatalog);
  const activeCounts = useTemplateStore((s) => s.activeCounts);
  const templateSelectedId = useTemplateStore((s) => s.selectedId);
  const templateComposite = useTemplateStore((s) => s.composite);
  const { data: catalog } = useQuery({
    queryKey: ["templates"],
    queryFn: getTemplates,
    staleTime: Infinity,
  });
  useEffect(() => {
    if (catalog) setCatalog(catalog.templates, catalog.themes);
  }, [catalog, setCatalog]);
  // Recompute the active quota set whenever the selection or composite edits change.
  const templateCounts = useMemo(
    () => activeCounts(),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [activeCounts, templateSelectedId, templateComposite],
  );

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

  // Auth: hydrate on mount; offer migrate-on-login when the user had a working deck.
  const { user, ready, refresh } = useAuth();
  const [migratePrompt, setMigratePrompt] = useState(false);
  const prevUser = useRef<number | null>(null);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // When the user transitions anonymous -> logged-in with a non-empty unsaved
  // working deck, offer to save it to their account.
  useEffect(() => {
    const was = prevUser.current;
    prevUser.current = user?.id ?? null;
    if (user && was == null && currentId == null && entries.length > 0) {
      setMigratePrompt(true);
    }
  }, [user, currentId, entries.length]);

  async function migrateWorkingDeck() {
    await saveDeck("Imported deck", commanderId, entries);
    setMigratePrompt(false);
  }

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
      {migratePrompt && (
        <div className="flex items-center justify-between gap-3 border-b border-accent/40 bg-accent/10 px-5 py-2 text-xs text-accent">
          <span>Save the deck you&apos;re building to your account?</span>
          <span className="flex gap-2">
            <button
              onClick={() => void migrateWorkingDeck()}
              className="rounded border border-accent/60 px-2 py-1 font-semibold hover:bg-accent/20"
            >
              Save it
            </button>
            <button
              onClick={() => setMigratePrompt(false)}
              className="rounded border border-edge px-2 py-1 text-zinc-400 hover:text-zinc-200"
            >
              Not now
            </button>
          </span>
        </div>
      )}
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
        templateCounts={templateCounts}
      />
      <TemplatePanel />
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
          <h1 className="font-display text-xl tracking-wide text-accent">
            Deck Doctor
          </h1>
          <span className="text-sm text-zinc-500">EDH deckbuilder · Simmander</span>
        </div>
        <div className="flex items-center gap-2">
          <UserMenu />
          <TemplateMenu />
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
          <div className="ml-1 text-xs text-zinc-500">{totalCards} cards · simmander.app/deck-doctor</div>
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
