"use client";

import { useEffect, useState } from "react";
import { postDeckComplete, postDeckCuts, fillLands } from "@/lib/api";
import { useDeck } from "@/store/deck";
import { ReasonChips } from "./SuggestionsPanel";
import type { Card, CompletionAdd, Cut, DeckEntry } from "@/lib/types";
import type { Zone as DeckZone } from "@/lib/zones";

type Tab = "complete" | "cuts" | "lands";

const PRICE_CAP_OPTIONS: { label: string; value: number }[] = [
  { label: "No cap", value: 0 },
  { label: "$10", value: 10 },
  { label: "$20", value: 20 },
  { label: "$30", value: 30 },
  { label: "$50", value: 50 },
  { label: "$100", value: 100 },
];

export function DeckDoctorPanel({
  isOpen,
  onClose,
  commander,
  entries,
  templateCounts,
}: {
  isOpen: boolean;
  onClose: () => void;
  commander: Card | null;
  entries: DeckEntry[];
  /** Active template quotas (from the header Template dropdown); fills toward these. */
  templateCounts?: Record<string, number> | null;
}) {
  const { add, move, remove, setBasic } = useDeck();
  const [tab, setTab] = useState<Tab>("complete");
  const [added, setAdded] = useState<CompletionAdd[] | null>(null);
  const [finalSize, setFinalSize] = useState(0);
  const [cuts, setCuts] = useState<Cut[] | null>(null);
  const [busy, setBusy] = useState(false);
  // Lands tab state
  const [landPriceCap, setLandPriceCap] = useState<number>(20);
  const [landsAdded, setLandsAdded] = useState<CompletionAdd[] | null>(null);
  const [landsFinalSize, setLandsFinalSize] = useState(0);

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [onClose]);

  if (!isOpen) return null;

  async function runComplete() {
    if (!commander) return;
    setBusy(true);
    try {
      const res = await postDeckComplete(entries, commander.id, templateCounts);
      // One click: apply straight to the board (Undo restores).
      for (const a of res.added) {
        const isBasic = (a.card.type_line || "").includes("Basic");
        if (isBasic) {
          setBasic(a.card.id, a.quantity, a.card);
        } else {
          add(a.card);
          move(a.card.id, a.zone as DeckZone);
        }
      }
      setAdded(res.added);
      setFinalSize(res.final_size);
    } finally {
      setBusy(false);
    }
  }

  function undoComplete() {
    if (!added) return;
    for (const a of added) {
      const isBasic = (a.card.type_line || "").includes("Basic");
      if (isBasic) setBasic(a.card.id, 0);
      else remove(a.card.id);
    }
    setAdded(null);
  }

  async function runFillLands() {
    if (!commander) return;
    setBusy(true);
    try {
      const res = await fillLands(entries, commander.id, landPriceCap, templateCounts);
      for (const a of res.added) {
        const isBasic = (a.card.type_line || "").includes("Basic");
        if (isBasic) {
          setBasic(a.card.id, a.quantity, a.card);
        } else {
          add(a.card);
          move(a.card.id, "Lands" as DeckZone);
        }
      }
      setLandsAdded(res.added);
      setLandsFinalSize(res.final_size);
    } finally {
      setBusy(false);
    }
  }

  function undoFillLands() {
    if (!landsAdded) return;
    for (const a of landsAdded) {
      const isBasic = (a.card.type_line || "").includes("Basic");
      if (isBasic) setBasic(a.card.id, 0);
      else remove(a.card.id);
    }
    setLandsAdded(null);
  }

  async function runCuts() {
    if (!commander) return;
    setBusy(true);
    try {
      const res = await postDeckCuts(entries, commander.id, 12);
      setCuts(res.cuts);
    } finally {
      setBusy(false);
    }
  }

  // Group the just-added cards by zone for the summary.
  const grouped: Record<string, CompletionAdd[]> = {};
  for (const a of added ?? []) (grouped[a.zone] ??= []).push(a);
  const maxContrib = Math.max(1e-6, ...(cuts ?? []).map((c) => c.contribution));

  return (
    <>
      <div className="fixed inset-0 z-[120] bg-black/40" onClick={onClose} />
      <div
        className="fixed right-0 top-0 z-[125] flex h-screen w-[460px] flex-col
                   border-l border-accent/30 bg-ink/90 shadow-neon backdrop-blur-md"
        data-testid="doctor-panel"
      >
        <div className="flex items-start justify-between border-b border-accent/30 px-4 py-3">
          <div>
            <p className="font-display text-[9px] uppercase tracking-wider text-accent">Deck Doctor</p>
            <p className="truncate text-sm font-semibold text-zinc-100">
              {commander ? commander.name : "no commander"}
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded p-1 text-zinc-500 transition hover:bg-accent/10 hover:text-accent"
          >
            ✕
          </button>
        </div>

        <div className="flex border-b border-accent/30 bg-ink/50">
          {(["complete", "lands", "cuts"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={[
                "flex-1 px-2 py-2 text-[11px] font-semibold uppercase tracking-wide transition",
                tab === t
                  ? "border-b-2 border-accent text-accent"
                  : "border-b-2 border-transparent text-[#9fd0ff] hover:text-cyan",
              ].join(" ")}
            >
              {t === "complete" ? "Complete" : t === "lands" ? "Lands" : "Cuts"}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto p-3 scrollbar-thin">
          {tab === "complete" && (
            <>
              <button
                data-testid="doctor-complete"
                onClick={runComplete}
                disabled={busy}
                className="mb-3 w-full rounded-lg bg-gradient-to-r from-magenta to-accent py-2 text-xs font-semibold
                           text-[#1a0033] shadow-neon transition hover:brightness-110 disabled:opacity-50"
              >
                {busy ? "Building…" : added ? "Complete again" : "Complete my deck"}
              </button>
              {added && (
                <>
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <p className="text-[11px] text-accent">
                      ✓ Added {added.reduce((s, a) => s + a.quantity, 0)} cards → {finalSize} (on the board)
                    </p>
                    <button
                      data-testid="doctor-undo"
                      onClick={undoComplete}
                      className="shrink-0 rounded border border-red-500/40 px-2 py-1 text-[10px]
                                 font-semibold text-red-400 transition hover:bg-red-500/10"
                    >
                      Undo
                    </button>
                  </div>
                  {Object.entries(grouped).map(([zone, items]) => (
                    <div key={zone} className="mb-2">
                      <p className="font-display text-[9px] uppercase tracking-wider text-accent">
                        {zone}
                      </p>
                      {items.map((a) => (
                        <div
                          key={a.card.id}
                          className="flex items-baseline justify-between gap-2 py-0.5 text-xs"
                        >
                          <span className="truncate text-zinc-300">
                            {a.card.name}
                            {a.quantity > 1 && (
                              <span className="ml-1 text-accent">×{a.quantity}</span>
                            )}
                          </span>
                          <span className="shrink-0 text-[9px] text-zinc-600">{a.reason}</span>
                        </div>
                      ))}
                    </div>
                  ))}
                </>
              )}
            </>
          )}

          {tab === "lands" && (
            <>
              {/* Price cap selector */}
              <div className="mb-3 flex items-center gap-2">
                <span className="shrink-0 font-display text-[9px] uppercase tracking-wider text-accent">
                  Price cap
                </span>
                <div className="flex flex-wrap gap-1">
                  {PRICE_CAP_OPTIONS.map((opt) => (
                    <button
                      key={opt.value}
                      onClick={() => setLandPriceCap(opt.value)}
                      className={[
                        "rounded border px-2 py-0.5 text-[10px] font-semibold transition",
                        landPriceCap === opt.value
                          ? "border-accent/70 bg-accent/20 text-accent"
                          : "border-zinc-700 text-zinc-500 hover:border-accent/40 hover:text-accent",
                      ].join(" ")}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>

              <button
                data-testid="doctor-fill-lands"
                onClick={runFillLands}
                disabled={busy || !commander}
                className="mb-3 w-full rounded-lg border border-accent/50 bg-accent/5 py-2
                           text-xs font-semibold text-accent transition
                           hover:bg-accent/15 disabled:opacity-50"
              >
                {busy ? "Filling lands…" : landsAdded ? "Fill lands again" : "Fill in my lands for me"}
              </button>

              {landsAdded && (
                <>
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <p className="text-[11px] text-accent">
                      ✓ Added {landsAdded.reduce((s, a) => s + a.quantity, 0)} lands → {landsFinalSize} total
                    </p>
                    <button
                      data-testid="doctor-undo-lands"
                      onClick={undoFillLands}
                      className="shrink-0 rounded border border-red-500/40 px-2 py-1 text-[10px]
                                 font-semibold text-red-400 transition hover:bg-red-500/10"
                    >
                      Undo
                    </button>
                  </div>
                  {landsAdded.length === 0 && (
                    <p className="py-4 text-center text-xs text-zinc-500">
                      Lands already at target — nothing to add.
                    </p>
                  )}
                  {/* Group by basic vs nonbasic */}
                  {(() => {
                    const basics = landsAdded.filter(a => (a.card.type_line || "").includes("Basic"));
                    const nonbasics = landsAdded.filter(a => !(a.card.type_line || "").includes("Basic"));
                    return (
                      <>
                        {nonbasics.length > 0 && (
                          <div className="mb-2">
                            <p className="font-display text-[9px] uppercase tracking-wider text-accent">
                              Nonbasic Lands
                            </p>
                            {nonbasics.map((a) => (
                              <div key={a.card.id} className="flex items-baseline justify-between gap-2 py-0.5 text-xs">
                                <span className="truncate text-zinc-300">{a.card.name}</span>
                                <span className="shrink-0 text-[9px] text-zinc-600">{a.reason}</span>
                              </div>
                            ))}
                          </div>
                        )}
                        {basics.length > 0 && (
                          <div className="mb-2">
                            <p className="font-display text-[9px] uppercase tracking-wider text-accent">
                              Basic Lands
                            </p>
                            {basics.map((a) => (
                              <div key={a.card.id} className="flex items-baseline justify-between gap-2 py-0.5 text-xs">
                                <span className="truncate text-zinc-300">
                                  {a.card.name}
                                  {a.quantity > 1 && (
                                    <span className="ml-1 text-accent">×{a.quantity}</span>
                                  )}
                                </span>
                                <span className="shrink-0 text-[9px] text-zinc-600">{a.reason}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </>
                    );
                  })()}
                </>
              )}

              {!commander && (
                <p className="py-4 text-center text-xs text-zinc-500">
                  Select a commander to fill lands.
                </p>
              )}
            </>
          )}

          {tab === "cuts" && (
            <>
              <button
                data-testid="doctor-cuts"
                onClick={runCuts}
                disabled={busy}
                className="mb-3 w-full rounded-lg border border-accent/50 py-2 text-xs font-semibold
                           text-accent transition hover:bg-accent/10 disabled:opacity-50"
              >
                {busy ? "Analyzing…" : "Suggest cuts"}
              </button>
              {cuts && cuts.length === 0 && (
                <p className="py-6 text-center text-xs text-zinc-500">
                  Nothing obvious to cut.
                </p>
              )}
              <ul className="space-y-2">
                {(cuts ?? []).map((c) => (
                  <li
                    key={c.card.id}
                    className="flex items-center gap-2 rounded-lg border border-accent/20 bg-ink/50 p-2"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-xs font-semibold text-zinc-200">
                        {c.card.name}
                      </p>
                      <div className="mt-0.5 h-1 w-full overflow-hidden rounded bg-panel2/60">
                        <div
                          className="h-full rounded bg-red-500/60"
                          style={{ width: `${(c.contribution / maxContrib) * 100}%` }}
                        />
                      </div>
                      <ReasonChips reasons={c.reasons} />
                    </div>
                    <button
                      onClick={() => remove(c.card.id)}
                      className="shrink-0 rounded-lg border border-red-500/40 px-2 py-1 text-[11px]
                                 font-semibold text-red-400 transition hover:bg-red-500/10"
                    >
                      Remove
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </div>
    </>
  );
}
