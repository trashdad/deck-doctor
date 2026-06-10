"use client";

import { useEffect, useState } from "react";
import { postDeckComplete, postDeckCuts } from "@/lib/api";
import { useDeck } from "@/store/deck";
import { ReasonChips } from "./SuggestionsPanel";
import type { Card, CompletionAdd, Cut, DeckEntry } from "@/lib/types";
import type { Zone as DeckZone } from "@/lib/zones";

type Tab = "complete" | "cuts";

export function DeckDoctorPanel({
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
  const { add, move, remove, setBasic } = useDeck();
  const [tab, setTab] = useState<Tab>("complete");
  const [added, setAdded] = useState<CompletionAdd[] | null>(null);
  const [finalSize, setFinalSize] = useState(0);
  const [cuts, setCuts] = useState<Cut[] | null>(null);
  const [busy, setBusy] = useState(false);

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
      const res = await postDeckComplete(entries, commander.id);
      setAdded(res.added);
      setFinalSize(res.final_size);
    } finally {
      setBusy(false);
    }
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

  function applyComplete() {
    if (!added) return;
    for (const a of added) {
      const isBasic = (a.card.type_line || "").includes("Basic");
      if (isBasic) {
        setBasic(a.card.id, a.quantity, a.card);
      } else {
        add(a.card);
        move(a.card.id, a.zone as DeckZone);
      }
    }
    setAdded(null);
    onClose();
  }

  // Group the completion preview by zone for readability.
  const grouped: Record<string, CompletionAdd[]> = {};
  for (const a of added ?? []) (grouped[a.zone] ??= []).push(a);
  const maxContrib = Math.max(1e-6, ...(cuts ?? []).map((c) => c.contribution));

  return (
    <>
      <div className="fixed inset-0 z-[120] bg-black/40" onClick={onClose} />
      <div
        className="fixed right-0 top-0 z-[125] flex h-screen w-[460px] flex-col
                   border-l border-edge bg-panel shadow-2xl"
        data-testid="doctor-panel"
      >
        <div className="flex items-start justify-between border-b border-edge px-4 py-3">
          <div>
            <p className="text-[9px] uppercase tracking-widest text-zinc-600">Deck Doctor</p>
            <p className="truncate text-sm font-semibold text-accent">
              {commander ? commander.name : "no commander"}
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded p-1 text-zinc-500 transition hover:bg-zinc-700 hover:text-zinc-200"
          >
            ✕
          </button>
        </div>

        <div className="flex border-b border-edge bg-zinc-900/50">
          {(["complete", "cuts"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={[
                "flex-1 px-2 py-2 text-[11px] font-semibold uppercase tracking-wide transition",
                tab === t
                  ? "border-b-2 border-accent text-accent"
                  : "border-b-2 border-transparent text-zinc-500 hover:text-zinc-300",
              ].join(" ")}
            >
              {t === "complete" ? "Complete" : "Cuts"}
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
                className="mb-3 w-full rounded-lg border border-accent/50 py-2 text-xs font-semibold
                           text-accent transition hover:bg-accent/10 disabled:opacity-50"
              >
                {busy ? "Building…" : "Complete my deck"}
              </button>
              {added && (
                <>
                  <p className="mb-2 text-[11px] text-zinc-400">
                    Adds {added.reduce((s, a) => s + a.quantity, 0)} cards → {finalSize}
                  </p>
                  {Object.entries(grouped).map(([zone, items]) => (
                    <div key={zone} className="mb-2">
                      <p className="text-[9px] font-bold uppercase tracking-widest text-zinc-600">
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
                  <button
                    data-testid="doctor-apply"
                    onClick={applyComplete}
                    className="mt-2 w-full rounded-lg bg-accent py-2 text-xs font-bold text-ink
                               transition hover:bg-accent/80"
                  >
                    Apply to deck
                  </button>
                </>
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
                    className="flex items-center gap-2 rounded-lg border border-edge bg-zinc-900/40 p-2"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-xs font-semibold text-zinc-200">
                        {c.card.name}
                      </p>
                      <div className="mt-0.5 h-1 w-full overflow-hidden rounded bg-white/5">
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
