"use client";

import { useEffect } from "react";
import type { Card, DeckCombos, Suggestion, SuggestionResponse } from "@/lib/types";
import type { CutRow } from "@/lib/cuts";
import type { PivotResponse } from "@/lib/pivot";
import { useUI, type RailTab, type RailView } from "@/store/ui";
import { RailTabs } from "./RailTabs";
import { SuggestTab } from "./rail/SuggestTab";
import { CutsTab } from "./rail/CutsTab";
import { TuneUpTab, type TuneUpTabProps } from "./rail/TuneUpTab";
import { CombosTab } from "./rail/CombosTab";
import { PivotTab } from "./rail/PivotTab";

export type { RailTab, RailView };

export interface RailMeta {
  /** From /health or a future /meta endpoint — never typed into the UI. */
  cardDataDate?: string;
  corpusDecks?: number;
  spellbookCombos?: number;
}

export interface DoctorRailProps {
  commander: Card | null;
  count: number;
  suggest: { tier: SuggestionResponse["tier"] | null; suggestions: Suggestion[]; loading?: boolean };
  cuts: {
    target: number;
    candidates: CutRow[];
    onTargetChange: (n: number) => void;
    /** to_100 response. undefined = not loaded (omit). null = the field was missing. */
    overBy?: number | null;
    shortfall?: number | null;
    loading?: boolean;
    error?: boolean;
    onCutAll?: (cards: Card[]) => void;
  };
  /** Omit → Pivot tab shows that no scores were requested. */
  pivot?: {
    data?: PivotResponse | null;
    loading?: boolean;
    error?: boolean;
    includeAll?: boolean;
    onIncludeAll?: (value: boolean) => void;
  };
  /** Omit → Combos tab shows its skeleton. */
  combos?: { data?: DeckCombos; loading?: boolean };
  /** Omit → Tune-up tab shows its skeleton. */
  tuneUp?: TuneUpTabProps;
  onAdd: (card: Card) => void;
  onCut: (card: Card) => void;
  meta?: RailMeta;
  /** "rail" = right column; "sheet" = mobile bottom sheet body (tabs rendered by the caller as a bar). */
  variant?: "rail" | "sheet";
  /** Pushed views (explorer, upgrade, …) render here in phase 2; the skeleton shows a back row. */
  renderView?: (view: RailView) => React.ReactNode;
  className?: string;
}

const fmt = (n: number | undefined) => (n === undefined ? "UNKNOWN" : n.toLocaleString());

/**
 * The persistent right rail (§4.1): tabs + nav stack + provenance footer.
 * Never covers the board; pushed views replace the tab body with a back arrow.
 * 1–5 switch tabs (global, outside inputs).
 */
export function DoctorRail({
  commander,
  count,
  suggest,
  cuts,
  pivot,
  combos,
  tuneUp,
  onAdd,
  onCut,
  meta,
  variant = "rail",
  renderView,
  className,
}: DoctorRailProps) {
  const tab = useUI((s) => s.railTab);
  const setTab = useUI((s) => s.setRailTab);
  const stack = useUI((s) => s.railStack);
  const popRail = useUI((s) => s.popRail);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (useUI.getState().menu || useUI.getState().sheet) return;
      const map: Record<string, RailTab> = { "1": "suggest", "2": "cuts", "3": "tuneup", "4": "combos", "5": "pivot" };
      const next = map[e.key];
      if (next) setTab(next);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setTab]);

  const top = stack[stack.length - 1];
  const hasCommander = commander !== null;

  const body = top ? (
    <div className="flex min-h-0 flex-1 flex-col">
      <button
        type="button"
        onClick={popRail}
        className="flex h-10 items-center gap-2 border-b border-edge px-3 text-[13px] font-semibold text-accent hover:bg-accent/10"
      >
        <span aria-hidden="true">←</span> Back
        <span className="ml-1 truncate text-[11px] font-normal uppercase tracking-wide text-zinc-400">
          {top.kind === "tab" ? top.tab : top.kind === "template" ? "Template" : `${top.kind} · ${top.card.name}`}
        </span>
      </button>
      {renderView ? renderView(top) : <p className="px-4 py-6 text-[13px] text-zinc-400">This view moves into the rail in phase 2.</p>}
    </div>
  ) : tab === "suggest" ? (
    <SuggestTab commander={commander} tier={suggest.tier} suggestions={suggest.suggestions} onAdd={onAdd} loading={suggest.loading} />
  ) : tab === "cuts" ? (
    <CutsTab
      commander={commander}
      count={count}
      target={cuts.target}
      onTargetChange={cuts.onTargetChange}
      candidates={cuts.candidates}
      onCut={onCut}
      onCutAll={cuts.onCutAll}
      overBy={cuts.overBy}
      shortfall={cuts.shortfall}
      loading={cuts.loading}
      error={cuts.error}
    />
  ) : tab === "tuneup" ? (
    <TuneUpTab {...tuneUp} hasCommander={hasCommander} />
  ) : tab === "combos" ? (
    <CombosTab hasCommander={hasCommander} data={combos?.data} loading={combos?.loading} onAdd={onAdd} />
  ) : (
    <PivotTab
      commander={commander}
      active={pivot != null}
      data={pivot?.data}
      loading={pivot?.loading}
      error={pivot?.error}
      includeAll={pivot?.includeAll}
      onIncludeAll={pivot?.onIncludeAll}
    />
  );

  return (
    <aside
      data-testid="doctor-rail"
      aria-label="Doctor"
      className={[
        "flex min-h-0 flex-col bg-panel-solid text-zinc-200",
        variant === "rail" ? "w-[400px] max-w-full border-l border-edge" : "w-full",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {variant === "rail" && <RailTabs value={tab} onChange={setTab} />}
      {body}
      <footer
        data-testid="rail-provenance"
        className="mt-auto border-t border-edge px-3 py-1.5 text-[11px] leading-[14px] text-zinc-400"
      >
        Card data: {meta?.cardDataDate ?? "UNKNOWN date"} · Corpus: {fmt(meta?.corpusDecks)} decks · Combos: Commander
        Spellbook {fmt(meta?.spellbookCombos)}
      </footer>
    </aside>
  );
}
