"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { DndContext, type DragEndEvent, PointerSensor, useSensor, useSensors } from "@dnd-kit/core";
import { useQuery } from "@tanstack/react-query";
import { SearchPanel } from "@/components/SearchPanel";
import { EngineBoard } from "@/components/EngineBoard";
import { StatsSidebar } from "@/components/StatsSidebar";
import { OraclePhrasePanel } from "@/components/OraclePhrasePanel";
import { SemanticFinder } from "@/components/SemanticFinder";
import { RelationshipExplorer } from "@/components/RelationshipExplorer";
import { CardUpgradePanel } from "@/components/CardUpgradePanel";
import { UpgradeSweepPanel } from "@/components/UpgradeSweepPanel";
import { SuggestionsPanel } from "@/components/SuggestionsPanel";
import { useSweepStore } from "@/store/sweep";
import { DeckManagerPanel } from "@/components/DeckManagerPanel";
import { ImportExportDialog } from "@/components/ImportExportDialog";
import { ImportDialog } from "@/components/ImportDialog";
import { DeckCombosPanel } from "@/components/DeckCombosPanel";
import { DeckDoctorPanel } from "@/components/DeckDoctorPanel";
import { SynergyGraph } from "@/components/SynergyGraph";
import { TemplatePanel } from "@/components/TemplatePanel";
import { ExportPanel } from "@/components/ExportPanel";
import { HowWeCalcModal } from "@/components/HowWeCalcModal";
import { UserMenu } from "@/components/UserMenu";
import { useDeck } from "@/store/deck";
import { useDecksStore } from "@/store/decks";
import { useTemplateStore } from "@/store/template";
import { useUI } from "@/store/ui";
import { useRelationshipStore } from "@/store/relationship";
import { useSemanticStore } from "@/store/semantic";
import { useAuth } from "@/store/auth";
import { useBackToClose } from "@/lib/useBackToClose";
import { ZONES, type Zone } from "@/lib/zones";
import type { EngineKey } from "@/components/EngineColumn";
import { analyzeDeck, getTemplates, useDiagnosis } from "@/lib/api";
import type { DeckEntry } from "@/lib/types";

function TemplateMenu() {
  const { templates, selectedId, select, openPanel } = useTemplateStore();
  const [open, setOpen] = useState(false);
  const current = templates.find((t) => t.id === selectedId);
  // Select a template AND jump straight into its options (skips the dropdown).
  const openOptions = (id: string) => {
    select(id);
    openPanel();
    setOpen(false);
  };
  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        data-testid="template-menu"
        title="Switch composition template"
        className="rounded-lg border border-accent/50 px-3 py-1.5 text-xs font-semibold tracking-wide
                   text-accent transition hover:bg-accent/10"
      >
        ⚜ {current?.name ?? "Template"} ▾
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-[130]" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-full z-[131] mt-1 w-72 rounded-lg border border-edge bg-panel p-1 shadow-2xl">
            {templates.map((t) => (
              <div
                key={t.id}
                className={[
                  "flex items-stretch rounded-md transition",
                  t.id === selectedId ? "bg-accent/15" : "hover:bg-white/5",
                ].join(" ")}
              >
                <button
                  data-testid={`template-opt-${t.id}`}
                  onClick={() => {
                    select(t.id);
                    setOpen(false);
                  }}
                  className="flex min-w-0 flex-1 flex-col rounded-l-md px-3 py-2 text-left"
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
                {/* Yellow arrow → open this template's options directly. */}
                <button
                  data-testid={`template-options-${t.id}`}
                  onClick={() => openOptions(t.id)}
                  title={`Open ${t.name} options`}
                  aria-label={`Open ${t.name} options`}
                  className="flex w-9 shrink-0 items-center justify-center rounded-r-md border-l
                             border-accent/30 bg-accent/10 text-sm font-bold text-accent
                             transition hover:bg-accent/30"
                >
                  ▸
                </button>
              </div>
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
  const { cards, basics, add, remove, move } = useDeck();
  const openTemplatePanel = useTemplateStore((s) => s.openPanel);
  const openSweep = useSweepStore((s) => s.open);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));
  const [suggestOpen, setSuggestOpen] = useState(false);
  const [decksOpen, setDecksOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [combosOpen, setCombosOpen] = useState(false);
  const [doctorOpen, setDoctorOpen] = useState(false);
  const [graphOpen, setGraphOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [howOpen, setHowOpen] = useState(false);

  // Store-backed overlays (for Back-to-close + the close-all dispatcher).
  const relationshipOpen = useRelationshipStore((s) => s.isOpen);
  const closeRelationship = useRelationshipStore((s) => s.close);
  const semanticOpen = useSemanticStore((s) => s.isOpen);
  const closeSemantic = useSemanticStore((s) => s.close);
  const engineStaplesOpen = useUI((s) => s.engineStaples != null);
  const closeEngineStaples = useUI((s) => s.closeEngineStaples);
  const winconHelperOpen = useUI((s) => s.winconHelperOpen);
  const closeWinconHelper = useUI((s) => s.closeWinconHelper);
  const templatePanelOpen = useTemplateStore((s) => s.panelOpen);
  const closeTemplatePanel = useTemplateStore((s) => s.closePanel);

  // OR of every major overlay. When true, the browser Back button dismisses the
  // topmost overlay (see useBackToClose) instead of leaving /deck-doctor.
  const anyOverlayOpen =
    suggestOpen ||
    decksOpen ||
    importOpen ||
    combosOpen ||
    doctorOpen ||
    graphOpen ||
    exportOpen ||
    howOpen ||
    relationshipOpen ||
    semanticOpen ||
    engineStaplesOpen ||
    winconHelperOpen ||
    templatePanelOpen;

  // Close every page + store overlay at once (Back-button handler target). The
  // per-card CardMenu is local to each card and closes itself on Escape, so it's
  // intentionally not covered here.
  const closeAllOverlays = useCallback(() => {
    setSuggestOpen(false);
    setDecksOpen(false);
    setImportOpen(false);
    setCombosOpen(false);
    setDoctorOpen(false);
    setGraphOpen(false);
    setExportOpen(false);
    setHowOpen(false);
    closeRelationship();
    closeSemantic();
    closeEngineStaples();
    closeWinconHelper();
    closeTemplatePanel();
  }, [
    closeRelationship,
    closeSemantic,
    closeEngineStaples,
    closeWinconHelper,
    closeTemplatePanel,
  ]);

  useBackToClose(anyOverlayOpen, closeAllOverlays);

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
    await useDecksStore.getState().saveCurrent("Imported deck");
    setMigratePrompt(false);
  }

  const { data: analysis } = useQuery({
    queryKey: ["analyze", entries.map((e) => `${e.id}:${e.quantity}`).sort().join(","), commanderId],
    queryFn: () => analyzeDeck(entries, commanderId),
    enabled: entries.length > 0,
  });

  // The headline "Deck Doctor Diagnosis" 0–100 score + vitals (Phase 4).
  const { data: diagnosis, isFetching: diagnosisLoading } = useDiagnosis(entries, commanderId);

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
    // BoardCard draggable ids are "bc::<cardId>::<variant>::<stackIndex>".
    // Strip back to just the card id.
    const rawId = String(e.active.id);
    const cardId = rawId.startsWith("bc::")
      ? rawId.split("::")[1] ?? rawId
      : rawId;

    if (!e.over) return;

    // Drop target id may be prefixed by engine key ("e1-", "e2-", "neutral-")
    const rawDropId = String(e.over.id);
    const engineKeys: EngineKey[] = ["e1", "e2", "neutral"];
    let zonePart = rawDropId;
    for (const ek of engineKeys) {
      if (rawDropId.startsWith(`${ek}-`)) {
        zonePart = rawDropId.slice(ek.length + 1);
        break;
      }
    }

    if (ZONES.includes(zonePart as Zone)) {
      move(cardId, zonePart as Zone);
    }
  }

  const totalCards = deckCards.length + basicCount;

  // Deck-action controls that live in the right of the commander pane (vertical).
  const paneBtn =
    "rounded-md border px-2 py-1 text-left text-[11px] font-semibold tracking-wide transition";
  const commanderControls = (
    <div className="flex w-40 flex-col gap-1">
      <TemplateMenu />
      <button
        data-testid="open-combos"
        title={deckCards.length ? "Combos in / near your deck" : "Add cards first"}
        disabled={deckCards.length === 0}
        onClick={() => setCombosOpen(true)}
        className={`${paneBtn} ${deckCards.length === 0 ? "cursor-not-allowed border-zinc-700 text-zinc-600" : "border-accent/50 text-accent hover:bg-accent/10"}`}
      >
        ♾ Combos
      </button>
      <button
        data-testid="open-doctor"
        title={commander ? "Deck Doctor" : "Add a commander first"}
        disabled={!commander}
        onClick={() => setDoctorOpen(true)}
        className={`${paneBtn} ${!commander ? "cursor-not-allowed border-zinc-700 text-zinc-600" : "border-accent/50 text-accent hover:bg-accent/10"}`}
      >
        🩺 Doctor
      </button>
      <button
        data-testid="open-suggestions"
        title={commander ? `Suggestions for ${commander.name}` : "Add a commander first"}
        disabled={!commander}
        onClick={() => setSuggestOpen(true)}
        className={`${paneBtn} ${!commander ? "cursor-not-allowed border-zinc-700 text-zinc-600" : "border-accent/50 text-accent hover:bg-accent/10"}`}
      >
        ⚡ Suggestions
      </button>
      <button
        data-testid="open-sweep"
        title={commander ? "Tune-up: swap the weakest cards for better ones" : "Add a commander first"}
        disabled={!commander}
        onClick={openSweep}
        className={`${paneBtn} ${!commander ? "cursor-not-allowed border-zinc-700 text-zinc-600" : "border-cyan/50 text-cyan hover:bg-cyan/10"}`}
      >
        ⬆ Tune-up
      </button>
    </div>
  );

  return (
    <div className="flex h-[100dvh] min-h-[100dvh] w-full flex-col overflow-hidden">
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
      <CardUpgradePanel />
      <UpgradeSweepPanel />
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
      <ImportDialog isOpen={importOpen} onClose={() => setImportOpen(false)} />
      <ImportExportDialog isOpen={false} onClose={() => {}} />
      <HowWeCalcModal isOpen={howOpen} onClose={() => setHowOpen(false)} />
      <ExportPanel
        isOpen={exportOpen}
        onClose={() => setExportOpen(false)}
        entries={entries}
        commanderId={commanderId}
      />

      <header className="flex items-center justify-between border-b border-accent/30 bg-[#0a0420]/70 px-5 py-3 backdrop-blur-md">
        <div className="flex items-baseline gap-3">
          <h1 className="arcade-bevel text-sm tracking-wide md:text-base">
            DECK DOCTOR
          </h1>
          <span className="text-xs uppercase tracking-[0.22em] text-cyan/70">
            EDH deckbuilder · Simmander
          </span>
        </div>
        <div className="flex items-center gap-2">
          <UserMenu />
          <HeaderButton testid="open-decks" title="Saved decks" onClick={() => setDecksOpen(true)}>
            🗂 Decks
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
            testid="open-import"
            title="Import a Moxfield or Archidekt decklist"
            onClick={() => setImportOpen(true)}
          >
            📥 Import
          </HeaderButton>
          <HeaderButton
            testid="open-export"
            title={totalCards > 0 ? "Export / share your deck" : "Add cards first"}
            disabled={totalCards === 0}
            onClick={() => setExportOpen(true)}
          >
            📤 Export
          </HeaderButton>
          <HeaderButton
            testid="open-how-we-calc"
            title="How we rate cards and make recommendations"
            onClick={() => setHowOpen(true)}
          >
            ❓ How We Calc
          </HeaderButton>
          <div className="ml-1 text-xs text-zinc-500">{totalCards} cards · simmander.app/deck-doctor</div>
        </div>
      </header>

      <DndContext sensors={sensors} onDragEnd={onDragEnd}>
        <div className="flex min-h-0 flex-1">
          <SearchPanel onAdd={add} />

          <EngineBoard commanderControls={commanderControls} />

          {/* Long options handle on the right margin of the board — opens the
              current template's options without touching the dropdown. */}
          <button
            onClick={openTemplatePanel}
            data-testid="template-options"
            title="Template options"
            className="flex w-8 shrink-0 items-center justify-center border-l border-accent/40
                       bg-accent/10 text-accent transition hover:bg-accent/25"
          >
            <span className="text-[10px] font-bold uppercase tracking-[0.3em] [writing-mode:vertical-rl]">
              ⚙ Template Options
            </span>
          </button>

          <StatsSidebar
            analysis={analysis ?? null}
            diagnosis={diagnosis ?? null}
            diagnosisLoading={diagnosisLoading}
          />
        </div>
      </DndContext>
    </div>
  );
}
