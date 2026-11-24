"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { analyzeDeck, postDeckCombos, recommendCards, upgradeSweep } from "@/lib/api";
import { clampCutTarget, postCutsTo100 } from "@/lib/cuts";
import { findCommanderPivots } from "@/lib/pivot";
import { useSweepStore } from "@/store/sweep";
import { toast } from "@/components/feedback/toastStore";
import { useUndoableDeck } from "@/hooks/useUndoableDeck";
import type { Card, DeckEntry } from "@/lib/types";
import { ZONES, type Zone } from "@/lib/zones";
import { MAX_HISTORY, undoLatestAction, useDeck } from "@/store/deck";
import { useUI, type RailTab } from "@/store/ui";
import { useTemplateStore } from "@/store/template";
import { useRelationshipStore } from "@/store/relationship";
import { DeckHeader } from "./DeckHeader";
import { DoctorRail } from "./DoctorRail";
import { RailTabs } from "./RailTabs";
import { BottomSheet } from "./BottomSheet";
import { useDesktop } from "./useDesktop";
import type { LedgerEntry } from "./RoleLedger";

/**
 * Data-connected workbench (MIGRATION.md step 5): DeckHeader + DoctorRail fed from the
 * real deck store and the same endpoints the drawers use. Mounted by page.tsx behind the
 * `workbench` flag; `children` is the board (EngineBoard).
 *
 * Layout (plan §4.1 / §4.9), rendered as siblings inside page.tsx's flex row/column:
 *   ≥ 1024 px  [board column: sticky DeckHeader over the board] [DoctorRail 400 px]
 *   < 1024 px  [board column] [RailTabs bar 56 px] + the rail as a BottomSheet (60/90 vh)
 *
 * Wired live:  header count / curve / ledger (deck store), bracket (`/deck/analyze`),
 *              Suggest (`/deck/recommend`), Cuts (`/deck/cuts?to_100=true`), Tune-up (`/deck/upgrade-sweep`),
 *              Combos (`/deck/combos`), Pivot (`/deck/pivot`, only while that tab is showing).
 *              Ledger quotas come from
 *              `useTemplateStore.activeCounts()` (filled by page.tsx's /templates query;
 *              defaults to the composite preset before that) for the five doctor categories;
 *              other zones have no quota (null). Template button → TemplatePanel (still a drawer).
 */
export const RAIL_BAR_HEIGHT = 56;
// Zone → template category (mirrors TemplatePanel.tsx CAT_ZONE). Zones without a category have no quota.
const ZONE_TO_CAT: Partial<Record<Zone, string>> = {
  Lands: "land",
  Ramp: "ramp",
  "Card Draw": "card_draw",
  Removal: "removal",
  "Board Wipes": "board_wipe",
};

export function WorkbenchLive({ children }: { children?: ReactNode }) {
  const cards = useDeck((s) => s.cards);
  const basics = useDeck((s) => s.basics);
  // Every rail mutation goes through the undoable wrappers, so each one gets the same
  // "… · Undo" toast as the context menu (review F-06).
  const undoable = useUndoableDeck();
  const openExplorer = useRelationshipStore((s) => s.open);
  const add = (card: Card) => void undoable.add(card);
  const swap = (targetId: string, replacement: Card) => {
    const target = useDeck.getState().cards[targetId]?.card;
    if (target) undoable.swap(target, replacement);
  };
  const setRailTab = useUI((s) => s.setRailTab);
  const railSheetOpen = useUI((s) => s.railSheetOpen);
  const setRailSheetOpen = useUI((s) => s.setRailSheetOpen);
  const desktop = useDesktop();
  const templateName = useTemplateStore((s) => s.templates.find((t) => t.id === s.selectedId)?.name);
  const openTemplatePanel = useTemplateStore((s) => s.openPanel);
  // null → default to how many cards the deck is over 100 (the route's `target`). A manual
  // target only holds while the deck size it was set at is unchanged (review F-08): once
  // the deck grows or shrinks the default (the new overage) applies again.
  const [cutTargetOverride, setCutTargetOverride] = useState<{ n: number; at: number } | null>(null);
  const [pivotIncludeAll, setPivotIncludeAll] = useState(false);
  // Mobile: the sheet opens on the tapped tab; tapping the showing tab again closes it.
  const openRailTab = (t: RailTab) => {
    if (!desktop && railSheetOpen && t === useUI.getState().railTab) {
      setRailSheetOpen(false);
      return;
    }
    setRailTab(t);
    if (!desktop) setRailSheetOpen(true);
  };
  // The sheet only exists < 1024 px; crossing to desktop closes it so the flag never
  // describes an invisible overlay (Back, re-open on resize — review F-13).
  useEffect(() => {
    if (desktop && useUI.getState().railSheetOpen) setRailSheetOpen(false);
  }, [desktop, setRailSheetOpen]);
  // < 1024 px the rail (and DoctorRail's 1–5 listener) only exists inside the open sheet,
  // so the shortcuts open the sheet on that tab from here (review F-22).
  useEffect(() => {
    if (desktop) return;
    const map: Record<string, RailTab> = { "1": "suggest", "2": "cuts", "3": "tuneup", "4": "combos", "5": "pivot" };
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const ui = useUI.getState();
      if (ui.menu || ui.sheet) return;
      const next = map[e.key];
      if (!next) return;
      setRailTab(next);
      setRailSheetOpen(true);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [desktop, setRailTab, setRailSheetOpen]);
  // Template quotas: same source page.tsx feeds DeckDoctorPanel (`templateCounts`). Keys are the
  // doctor categories (land/ramp/card_draw/removal/board_wipe); mapped to zones as TemplatePanel's CAT_ZONE does.
  const activeCounts = useTemplateStore((s) => s.activeCounts);
  const templateSelectedId = useTemplateStore((s) => s.selectedId);
  const templateComposite = useTemplateStore((s) => s.composite);
  const quotas = useMemo(
    () => activeCounts(),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [activeCounts, templateSelectedId, templateComposite],
  );

  const deckCards = useMemo(() => Object.values(cards), [cards]);
  const basicSig = Object.entries(basics)
    .map(([id, b]) => `${id}:${b.quantity}`)
    .join(",");

  const entries: DeckEntry[] = useMemo(() => {
    const out: DeckEntry[] = deckCards.map((dc) => ({ id: dc.card.id, zone: dc.zone, quantity: 1 }));
    for (const [id, b] of Object.entries(basics)) out.push({ id, zone: "Lands", quantity: b.quantity });
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deckCards, basicSig]);

  const commander: Card | null = deckCards.find((dc) => dc.zone === "Commanders")?.card ?? null;
  const commanderId = commander?.id ?? null;
  const basicCount = Object.values(basics).reduce((s, b) => s + b.quantity, 0);
  const count = deckCards.length + basicCount;
  const overByLocal = Math.max(0, count - 100);
  const cutTarget =
    cutTargetOverride && cutTargetOverride.at === count ? cutTargetOverride.n : clampCutTarget(overByLocal || 1);
  const sig = entries.map((e) => `${e.id}:${e.quantity}`).sort().join(",");

  const ledger: LedgerEntry[] = useMemo(() => {
    const have: Record<string, number> = {};
    for (const dc of deckCards) have[dc.zone] = (have[dc.zone] ?? 0) + 1;
    have.Lands = (have.Lands ?? 0) + basicCount;
    return ZONES.filter((z) => z !== "Commanders").map((zone) => {
      const cat = ZONE_TO_CAT[zone];
      const q = cat ? quotas[cat] : undefined;
      return { zone, have: have[zone] ?? 0, quota: typeof q === "number" ? q : null };
    });
  }, [deckCards, basicCount, quotas]);

  // Curve from the cards in hand (basics are 0-drops and are left out, as the sidebar does).
  const curve = useMemo(() => {
    const bins: Record<number, number> = {};
    for (const dc of deckCards) {
      if (dc.zone === "Commanders") continue;
      const c = Math.round(dc.card.cmc ?? 0);
      bins[c] = (bins[c] ?? 0) + 1;
    }
    return Object.entries(bins).map(([cmc, n]) => ({ cmc: Number(cmc), count: n }));
  }, [deckCards]);

  const analysis = useQuery({
    queryKey: ["analyze", sig, commanderId],
    queryFn: () => analyzeDeck(entries, commanderId),
    enabled: entries.length > 0,
    staleTime: 30_000,
  });
  const bracket = analysis.data ? { floor: analysis.data.bracket, flags: analysis.data.bracket_reasons } : null;

  const suggest = useQuery({
    queryKey: ["suggest", commanderId, sig],
    queryFn: () => recommendCards(entries, commanderId!, { limit: 24, explain: true }),
    enabled: commanderId != null,
    staleTime: 30_000,
    // Keep the rows while the next ranking loads (no list teardown / focus loss — review F-11).
    placeholderData: keepPreviousData,
  });
  // Hide anything added since the last fetch so the list reacts instantly.
  const suggestions = (suggest.data?.suggestions ?? []).filter((s) => !cards[s.card.id]);

  const quotaSig = JSON.stringify(quotas);
  const cuts = useQuery({
    queryKey: ["cuts-to-100", commanderId, sig, cutTarget, quotaSig],
    queryFn: () => postCutsTo100(entries, commanderId!, cutTarget, { template: quotas }),
    enabled: commanderId != null && count > 100,
    staleTime: 30_000,
    // Keep the rows while re-ranking after a cut (review F-11), but not once the deck is ≤ 100.
    placeholderData: (prev) => (count > 100 ? prev : undefined),
  });
  // Rows must still be in the deck, and a commander (or partner) is never a cut (review F-04).
  const candidates = (cuts.data?.cuts ?? []).filter((c) => {
    const dc = cards[c.card.id];
    return dc ? dc.zone !== "Commanders" : !!basics[c.card.id];
  });

  // Same endpoint/key shape as DeckCombosPanel; only fetched while the Combos tab is showing.
  const railTab = useUI((s) => s.railTab);
  const combos = useQuery({
    queryKey: ["deck-combos", commanderId, entries.map((e) => e.id).sort().join(",")],
    queryFn: () => postDeckCombos(entries, commanderId),
    enabled: railTab === "combos" && entries.length > 0,
    staleTime: 30_000,
  });

  // Same endpoint/key shape as UpgradeSweepPanel (shares its slider/synergy settings via useSweepStore);
  // only fetched while the Tune-up tab is showing.
  const sweepEfficiency = useSweepStore((s) => s.efficiency);
  const sweepSynergy = useSweepStore((s) => s.favorSynergy);
  const sweep = useQuery({
    queryKey: ["sweep", commanderId, sig, sweepEfficiency, sweepSynergy],
    queryFn: () => upgradeSweep(entries, commanderId!, { efficiency: sweepEfficiency, favorSynergy: sweepSynergy, weak: 16 }),
    enabled: railTab === "tuneup" && commanderId != null,
    staleTime: 30_000,
  });
  const sweepData = sweep.data
    ? { ...sweep.data, swaps: (sweep.data.swaps ?? []).filter((s) => !!cards[s.target.id]) }
    : undefined;

  const pivot = useQuery({
    queryKey: ["pivot", commanderId, sig, pivotIncludeAll],
    queryFn: () => findCommanderPivots(entries, commanderId, { includeAll: pivotIncludeAll, limit: 10 }),
    enabled: railTab === "pivot" && commanderId != null,
    staleTime: 30_000,
  });

  // store.remove drops one copy of a basic, so this covers singleton and basic rows alike.
  const cutOne = (card: Card) => {
    if (useDeck.getState().cards[card.id]?.zone === "Commanders") return;
    undoable.remove(card);
  };

  // One history entry for the whole batch, so a single Undo restores every card.
  const cutAll = (list: Card[]) => {
    const s = useDeck.getState();
    const nextCards = { ...s.cards };
    const nextBasics = { ...s.basics };
    const removed: string[] = [];
    for (const card of list) {
      if (nextCards[card.id]?.zone === "Commanders") continue; // never cut a commander (F-04)
      if (nextCards[card.id]) {
        delete nextCards[card.id];
        removed.push(card.name);
      } else {
        const basic = nextBasics[card.id];
        if (basic && basic.quantity > 0) {
          const q = basic.quantity - 1;
          if (q <= 0) delete nextBasics[card.id];
          else nextBasics[card.id] = { card: basic.card, quantity: q };
          removed.push(card.name);
        }
      }
    }
    if (removed.length === 0) return;
    useDeck.setState({
      cards: nextCards,
      basics: nextBasics,
      history: [...s.history.slice(-(MAX_HISTORY - 1)), { cards: s.cards, basics: s.basics }],
      future: [],
    });
    toast({
      message: removed.length === 1 ? `Removed ${removed[0]}` : `Cut ${removed.length} cards`,
      action: { label: "Undo", onClick: undoLatestAction() },
    });
  };

  const rail = (
    <DoctorRail
      commander={commander}
      count={count}
      suggest={{ tier: suggest.data?.tier ?? null, suggestions, loading: suggest.isFetching, error: suggest.isError }}
      cuts={{
        target: cutTarget,
        candidates,
        onTargetChange: (n) => setCutTargetOverride({ n: clampCutTarget(n), at: count }),
        overBy: cuts.data ? (typeof cuts.data.over_by === "number" ? cuts.data.over_by : null) : undefined,
        shortfall: cuts.data ? (typeof cuts.data.shortfall === "number" ? cuts.data.shortfall : null) : undefined,
        loading: cuts.isLoading,
        error: cuts.isError,
        onCutAll: cutAll,
      }}
      pivot={{
        data: pivot.data ?? null,
        loading: pivot.isLoading,
        error: pivot.isError,
        includeAll: pivotIncludeAll,
        onIncludeAll: setPivotIncludeAll,
      }}
      combos={{ data: combos.data, loading: combos.isFetching, error: combos.isError }}
      tuneUp={{
        hasCommander: commanderId != null,
        data: sweepData,
        loading: sweep.isFetching,
        error: sweep.error != null,
        onSwap: swap,
      }}
      onAdd={add}
      onCut={cutOne}
      onOpenCard={(card) => openExplorer(card, "similar")}
      variant={desktop ? "rail" : "sheet"}
      // Row child on desktop (fixed 400 px, no grow); column child inside the sheet.
      className={desktop ? "min-h-0 shrink-0" : "min-h-0 flex-1"}
    />
  );

  return (
    <>
      <div data-testid="workbench-live" className="flex min-h-0 min-w-0 flex-1 flex-col">
        <DeckHeader
          commander={commander}
          count={count}
          target={100}
          ledger={ledger}
          curve={curve}
          bracket={bracket}
          bracketError={analysis.isError}
          templateName={templateName}
          onOpenTemplate={openTemplatePanel}
          onOpenCuts={(n) => {
            setCutTargetOverride({ n: clampCutTarget(n), at: count });
            openRailTab("cuts");
          }}
          onOpenComplete={() => openRailTab("suggest")}
          onJumpToLane={(zone: Zone) => {
            // Lanes carry data-zone on their FieldSection title; scroll the first match into view.
            document.querySelector(`[data-zone-lane="${zone}"]`)?.scrollIntoView({ block: "start", behavior: "smooth" });
          }}
          onFlagClick={() => openRailTab("cuts")}
        />
        {children}
      </div>
      {desktop ? (
        rail
      ) : (
        <>
          <div className="shrink-0" style={{ height: RAIL_BAR_HEIGHT }}>
            <RailTabs value={railTab} onChange={openRailTab} variant="bar" />
          </div>
          <BottomSheet
            open={railSheetOpen}
            onClose={() => setRailSheetOpen(false)}
            label="Doctor"
            bottomOffset={RAIL_BAR_HEIGHT}
            testid="rail-sheet"
          >
            {rail}
          </BottomSheet>
        </>
      )}
    </>
  );
}
