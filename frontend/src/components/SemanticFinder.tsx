"use client";

import { useEffect, useRef } from "react";
import { useSemanticStore } from "@/store/semantic";
import { useDeck } from "@/store/deck";
import { CardTile } from "./CardTile";
import { getTagMeta, groupTagsByCategory, TAG_GROUPS } from "@/lib/tags";
import type { TagGroup } from "@/lib/tags";
import type { Card } from "@/lib/types";

/** Chain-link icon — two connected rings */
function ChainIcon({ active }: { active: boolean }) {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke={active ? "#c9a227" : "#4b5563"}
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="shrink-0"
    >
      <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
      <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
    </svg>
  );
}

function TagChip({
  tag,
  selected,
  linked,
  onToggle,
  onToggleLinked,
}: {
  tag: string;
  selected: boolean;
  linked: boolean;
  onToggle: () => void;
  onToggleLinked: (e: React.MouseEvent) => void;
}) {
  const meta = getTagMeta(tag);
  return (
    <div
      className={[
        "flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium",
        "cursor-pointer select-none transition",
        selected
          ? "border border-transparent text-white"
          : "border border-zinc-700 text-zinc-500 hover:border-zinc-500 hover:text-zinc-300",
      ].join(" ")}
      style={selected ? { background: meta.color + "33", borderColor: meta.color } : {}}
      onClick={onToggle}
      title={tag}
    >
      {selected && (
        <button
          onClick={onToggleLinked}
          title={linked ? "Unlink (tag can appear anywhere)" : "Link (tag must be same ability line)"}
          className="mr-0.5 shrink-0 opacity-90 hover:opacity-100"
        >
          <ChainIcon active={linked} />
        </button>
      )}
      <span>{meta.label}</span>
    </div>
  );
}

function GroupSection({
  group,
  tags,
  selectedTags,
  linkedTags,
  onToggle,
  onToggleLinked,
}: {
  group: TagGroup;
  tags: string[];
  selectedTags: Set<string>;
  linkedTags: Set<string>;
  onToggle: (tag: string) => void;
  onToggleLinked: (tag: string) => void;
}) {
  if (tags.length === 0) return null;
  return (
    <div className="mb-3">
      <p className="mb-1.5 text-[9px] font-bold uppercase tracking-widest text-zinc-600">
        {group}
      </p>
      <div className="flex flex-wrap gap-1.5">
        {tags.map((tag) => (
          <TagChip
            key={tag}
            tag={tag}
            selected={selectedTags.has(tag)}
            linked={linkedTags.has(tag)}
            onToggle={() => onToggle(tag)}
            onToggleLinked={(e) => {
              e.stopPropagation();
              onToggleLinked(tag);
            }}
          />
        ))}
      </div>
    </div>
  );
}

export function SemanticFinder() {
  const {
    isOpen,
    activeCard,
    semantics,
    loading,
    selectedTags,
    linkedTags,
    results,
    searching,
    close,
    toggleTag,
    toggleLinked,
    runSearch,
  } = useSemanticStore();

  const { add } = useDeck();
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [close]);

  if (!isOpen) return null;

  const flatTags = semantics?.flat_tags ?? [];
  const grouped = groupTagsByCategory(flatTags);
  const linkedCount = linkedTags.size;
  const flatCount = selectedTags.size - linkedCount;
  const hasSelection = selectedTags.size > 0;

  const buildQuerySummary = () => {
    const parts: string[] = [];
    if (linkedCount > 0) {
      const labels = [...linkedTags].map((t) => getTagMeta(t).label).join(" + ");
      parts.push(`linked: ${labels}`);
    }
    if (flatCount > 0) {
      const flatTags2 = [...selectedTags]
        .filter((t) => !linkedTags.has(t))
        .map((t) => getTagMeta(t).label)
        .join(", ");
      parts.push(flatTags2);
    }
    return parts.join("  ·  ");
  };

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-[90] bg-black/40"
        onClick={close}
      />

      {/* Panel */}
      <div
        ref={panelRef}
        className="fixed right-0 top-0 z-[95] flex h-full w-[420px] flex-col
                   border-l border-edge bg-panel shadow-2xl"
      >
        {/* Header */}
        <div className="flex items-start justify-between border-b border-edge px-4 py-3">
          <div className="min-w-0 flex-1">
            <p className="text-[9px] uppercase tracking-widest text-zinc-600">
              Semantic Finder
            </p>
            <p className="truncate text-sm font-semibold text-accent">
              {activeCard?.name ?? ""}
            </p>
            {activeCard?.type_line && (
              <p className="text-[10px] text-zinc-500">{activeCard.type_line}</p>
            )}
          </div>
          <button
            onClick={close}
            className="ml-3 shrink-0 rounded-full p-1 text-zinc-500
                       transition hover:bg-white/10 hover:text-zinc-200"
          >
            ✕
          </button>
        </div>

        {/* Instructions */}
        <div className="border-b border-edge bg-zinc-900/60 px-4 py-2">
          <p className="text-[10px] leading-relaxed text-zinc-500">
            Click tags to select them. Click{" "}
            <ChainIcon active={true} />
            {" "}to require those tags to appear on the <em>same ability line</em>.
            Unlinked tags may appear anywhere on the card.
          </p>
        </div>

        {/* Tag selector */}
        <div className="flex-1 overflow-y-auto px-4 py-3 scrollbar-thin">
          {loading && (
            <p className="text-xs text-zinc-500">Loading semantic tags…</p>
          )}
          {!loading && flatTags.length === 0 && (
            <p className="text-xs text-zinc-500">
              No semantic data for this card.
            </p>
          )}
          {!loading &&
            TAG_GROUPS.map((group) => (
              <GroupSection
                key={group}
                group={group}
                tags={grouped[group]}
                selectedTags={selectedTags}
                linkedTags={linkedTags}
                onToggle={toggleTag}
                onToggleLinked={toggleLinked}
              />
            ))}

          {/* Ability breakdown */}
          {semantics && semantics.ability_tags.length > 0 && (
            <details className="mt-2">
              <summary className="cursor-pointer text-[9px] uppercase tracking-widest text-zinc-600 hover:text-zinc-400">
                Per-ability breakdown
              </summary>
              <div className="mt-2 space-y-1.5">
                {semantics.ability_tags.map((abilityTags, i) =>
                  abilityTags.length === 0 ? null : (
                    <div key={i} className="flex flex-wrap gap-1">
                      <span className="text-[9px] text-zinc-600">#{i + 1}</span>
                      {abilityTags.map((tag) => {
                        const m = getTagMeta(tag);
                        return (
                          <span
                            key={tag}
                            className="rounded px-1 py-0.5 text-[9px]"
                            style={{ background: m.color + "22", color: m.color }}
                          >
                            {m.label}
                          </span>
                        );
                      })}
                    </div>
                  ),
                )}
              </div>
            </details>
          )}
        </div>

        {/* Find button + query summary */}
        <div className="border-t border-edge px-4 py-3">
          {hasSelection && (
            <p className="mb-2 text-[10px] leading-snug text-zinc-500">
              {buildQuerySummary()}
            </p>
          )}
          <button
            onClick={runSearch}
            disabled={!hasSelection || searching}
            className={[
              "w-full rounded-lg py-2.5 text-xs font-bold uppercase tracking-widest transition",
              hasSelection
                ? "bg-accent text-ink hover:bg-accent/80"
                : "cursor-not-allowed bg-zinc-800 text-zinc-600",
            ].join(" ")}
          >
            {searching ? "Searching…" : "Find Cards"}
          </button>
        </div>

        {/* Results */}
        {(results !== null || searching) && (
          <div className="max-h-[45vh] overflow-y-auto border-t border-edge scrollbar-thin">
            {searching && (
              <p className="px-4 py-3 text-xs text-zinc-500">Searching…</p>
            )}
            {results !== null && results.length === 0 && (
              <p className="px-4 py-3 text-xs text-zinc-500">No cards found.</p>
            )}
            {results !== null && results.length > 0 && (
              <>
                <p className="px-4 pt-2 text-[10px] text-zinc-500">
                  {results.length} cards found — click to add
                </p>
                <div className="grid grid-cols-3 gap-2 p-3">
                  {results.map((card: Card) => (
                    <CardTile
                      key={card.id}
                      card={card}
                      compact
                      onClick={() => add(card)}
                    />
                  ))}
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </>
  );
}
