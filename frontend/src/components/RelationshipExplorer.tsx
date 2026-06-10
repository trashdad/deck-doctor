"use client";

import { useEffect } from "react";
import { useRelationshipStore, type ExplorerAxis } from "@/store/relationship";
import { useDeck } from "@/store/deck";
import { CardTile } from "./CardTile";
import type { Card, PairScoreFull } from "@/lib/types";

const AXES: { key: ExplorerAxis; label: string; gloss: string }[] = [
  { key: "similar", label: "Similar", gloss: "does the same job (SP1 similarity)" },
  { key: "synergy", label: "Synergizes", gloss: "enables / is enabled by (SP1 synergy)" },
  { key: "cooccurrence", label: "Played with", gloss: "empirically run together (deck lift)" },
  { key: "combos", label: "Combos", gloss: "asserted combos & candidate engines" },
  { key: "tags", label: "Tag-sim", gloss: "semantic tag overlap (legacy TF-IDF)" },
];

function metricBadge(axis: ExplorerAxis, metric: number): string {
  if (axis === "similar") return `sim ${metric.toFixed(2)}`;
  if (axis === "synergy") return `syn ${metric.toFixed(2)}`;
  return `lift ${metric.toFixed(1)}`;
}

function EdgeRow({
  label,
  value,
  gloss,
}: {
  label: string;
  value: string | null;
  gloss: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-2 py-0.5">
      <span className="shrink-0 text-[10px] font-semibold uppercase tracking-wider text-zinc-400">
        {label}
      </span>
      <span className="flex-1 truncate text-right text-[9px] text-zinc-600">{gloss}</span>
      <span className="w-12 shrink-0 text-right text-[11px] font-bold text-accent">
        {value ?? "—"}
      </span>
    </div>
  );
}

function PairReadout({
  focal,
  card,
  pair,
  loading,
  onClose,
}: {
  focal: Card;
  card: Card;
  pair: PairScoreFull | null;
  loading: boolean;
  onClose: () => void;
}) {
  const rel = pair?.relationship ?? null;
  const co = pair?.cooccurrence ?? null;
  return (
    <div className="mb-3 rounded-lg border border-accent/40 bg-zinc-900/80 px-3 py-2">
      <div className="mb-1 flex items-center justify-between">
        <p className="truncate text-[10px] font-semibold uppercase tracking-widest text-accent">
          {focal.name} ⟷ {card.name}
        </p>
        <button
          onClick={onClose}
          className="ml-2 shrink-0 rounded p-0.5 text-zinc-500 hover:bg-white/10 hover:text-zinc-200"
        >
          ✕
        </button>
      </div>
      {loading && <p className="py-2 text-[10px] text-zinc-500">Loading edge…</p>}
      {!loading && !pair && (
        <p className="py-2 text-[10px] text-zinc-500">No edge data for this pair.</p>
      )}
      {!loading && pair && (
        <div className="divide-y divide-white/5">
          <EdgeRow
            label="Similarity"
            gloss="same mechanical job"
            value={rel ? rel.similarity.toFixed(2) : null}
          />
          <EdgeRow
            label="Synergy →"
            gloss={`${focal.name} enables ${card.name}`}
            value={rel ? rel.synergy_ab.toFixed(2) : null}
          />
          <EdgeRow
            label="Synergy ←"
            gloss={`${card.name} enables ${focal.name}`}
            value={rel ? rel.synergy_ba.toFixed(2) : null}
          />
          <EdgeRow
            label="Anti-synergy"
            gloss="works against each other"
            value={rel ? rel.anti_synergy.toFixed(2) : null}
          />
          <EdgeRow
            label="Combo"
            gloss="asserted combo pair"
            value={rel ? (rel.combo ? "yes" : "no") : null}
          />
          <EdgeRow
            label="Decks together"
            gloss="co-occurrence count"
            value={co ? String(co.co_count) : null}
          />
          <EdgeRow
            label="Lift"
            gloss=">1 = run together more than chance"
            value={co ? co.lift.toFixed(2) : null}
          />
          <EdgeRow
            label="Jaccard"
            gloss="overlap of their deck sets"
            value={co ? co.jaccard.toFixed(3) : null}
          />
        </div>
      )}
    </div>
  );
}

export function RelationshipExplorer() {
  const {
    isOpen,
    focal,
    axis,
    stack,
    data,
    inspect,
    loading,
    setAxis,
    pivot,
    back,
    inspectCard,
    closeInspect,
    close,
  } = useRelationshipStore();
  const { add } = useDeck();

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [close]);

  if (!isOpen || !focal) return null;

  const activeAxis = AXES.find((a) => a.key === axis)!;
  const neighbors = data?.neighbors ?? null;
  const engines = data?.engines ?? null;
  const tagSimilar = data?.tagSimilar ?? null;

  return (
    <>
      <div
        className="fixed inset-0 z-[140] bg-black/40 backdrop-blur-[1px]"
        onClick={close}
        data-testid="explorer-backdrop"
      />

      <div
        className="fixed right-0 top-0 z-[145] flex h-screen w-[460px] flex-col
                   border-l border-edge bg-panel shadow-2xl"
        data-testid="relationship-explorer"
      >
        {/* Header */}
        <div className="flex items-start gap-2 border-b border-edge px-4 py-3">
          {stack.length > 0 && (
            <button
              onClick={back}
              title={`Back to ${stack[stack.length - 1].name}`}
              data-testid="explorer-back"
              className="mt-0.5 shrink-0 rounded p-1 text-accent transition hover:bg-accent/10"
            >
              ‹
            </button>
          )}
          <div className="min-w-0 flex-1">
            <p className="text-[9px] uppercase tracking-widest text-zinc-600">
              Relationship Explorer
              {stack.length > 0 && (
                <span className="ml-1 text-zinc-700">
                  · {stack.map((c) => c.name).join(" › ")} ›
                </span>
              )}
            </p>
            <p className="truncate text-sm font-semibold text-accent">{focal.name}</p>
            <p className="text-[10px] text-zinc-500">
              {focal.type_line}
              {focal.ier != null && <span className="ml-2 text-accent/70">IER {focal.ier}</span>}
            </p>
          </div>
          <button
            onClick={close}
            className="ml-2 mt-0.5 shrink-0 rounded p-1 text-zinc-500 transition hover:bg-zinc-700 hover:text-zinc-200"
          >
            ✕
          </button>
        </div>

        {/* Axis tabs */}
        <div className="flex border-b border-edge bg-zinc-900/50">
          {AXES.map((a) => (
            <button
              key={a.key}
              onClick={() => setAxis(a.key)}
              data-testid={`axis-${a.key}`}
              className={[
                "flex-1 px-1 py-2 text-[10px] font-semibold uppercase tracking-wide transition",
                axis === a.key
                  ? "border-b-2 border-accent text-accent"
                  : "border-b-2 border-transparent text-zinc-500 hover:text-zinc-300",
              ].join(" ")}
            >
              {a.label}
            </button>
          ))}
        </div>
        <p className="border-b border-edge px-4 py-1.5 text-[9px] text-zinc-600">
          {activeAxis.gloss}
        </p>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-3 scrollbar-thin">
          {inspect && (
            <PairReadout
              focal={focal}
              card={inspect.card}
              pair={inspect.pair}
              loading={inspect.loading}
              onClose={closeInspect}
            />
          )}

          {loading && (
            <div className="flex items-center justify-center py-12">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-accent border-t-transparent" />
            </div>
          )}

          {/* Typed-axis neighbor grid */}
          {!loading && neighbors && neighbors.length > 0 && (
            <div className="grid grid-cols-3 gap-2">
              {neighbors.map(({ card, metric }) => (
                <CardTile
                  key={card.id}
                  card={card}
                  compact
                  badge={metricBadge(axis, metric)}
                  onClick={() => inspectCard(card)}
                  onAdd={() => add(card)}
                  onFocus={() => pivot(card)}
                  onInspect={() => inspectCard(card)}
                />
              ))}
            </div>
          )}
          {!loading && neighbors && neighbors.length === 0 && (
            <p className="py-8 text-center text-xs text-zinc-500">
              No {activeAxis.label.toLowerCase()} neighbors recorded for this card.
            </p>
          )}

          {/* Combos / engines */}
          {!loading && engines && engines.length > 0 && (
            <div className="space-y-3">
              {engines.map((g) => (
                <div
                  key={g.engine_id}
                  className="rounded-lg border border-edge bg-zinc-900/50 p-2"
                >
                  <div className="mb-1.5 flex items-center gap-2">
                    {g.asserted && <span title="asserted combo">⭐</span>}
                    <span className="rounded bg-accent/15 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-accent">
                      {g.asserted ? "combo" : `${g.kind} engine`}
                    </span>
                    {g.candidate && !g.asserted && (
                      <span className="text-[9px] text-zinc-600">candidate</span>
                    )}
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    {g.members.map((m) => (
                      <CardTile
                        key={`${g.engine_id}:${m.id}`}
                        card={m}
                        compact
                        onClick={() => m.id !== focal.id && inspectCard(m)}
                        onAdd={() => add(m)}
                        onFocus={m.id !== focal.id ? () => pivot(m) : undefined}
                        onInspect={m.id !== focal.id ? () => inspectCard(m) : undefined}
                      />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
          {!loading && engines && engines.length === 0 && (
            <p className="py-8 text-center text-xs text-zinc-500">
              No combos or engines recorded for this card.
            </p>
          )}

          {/* Legacy tag similarity */}
          {!loading && tagSimilar && tagSimilar.length > 0 && (
            <div className="grid grid-cols-3 gap-2">
              {tagSimilar.map((card) => (
                <CardTile
                  key={card.id}
                  card={card}
                  compact
                  onClick={() => inspectCard(card)}
                  onAdd={() => add(card)}
                  onFocus={() => pivot(card)}
                  onInspect={() => inspectCard(card)}
                />
              ))}
            </div>
          )}
          {!loading && tagSimilar && tagSimilar.length === 0 && (
            <p className="py-8 text-center text-xs text-zinc-500">
              No semantic tags for this card yet.
            </p>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-edge px-4 py-2 text-[10px] text-zinc-500">
          ＋ add · ◎ focus · ⓘ inspect pair
        </div>
      </div>
    </>
  );
}
