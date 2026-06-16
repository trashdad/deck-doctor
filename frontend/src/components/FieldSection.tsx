"use client";

import { useDroppable } from "@dnd-kit/core";
import type { Zone } from "@/lib/zones";
import type { PileEntry } from "./CardPile";
import { CardPile } from "./CardPile";

interface Props {
  zone: Zone;
  /** Unique drop-target id (zone name is sufficient for non-composite; in
   *  composite we append the engine key so both columns have distinct ids). */
  dropId: string;
  entries: PileEntry[];
  onRemove?: (cardId: string) => void;
  /** Optional CSS variable tint colour (e.g. rgba(239,68,68,0.08)). */
  tint?: string;
}

/**
 * One function subsection inside an engine column (or the single-column view).
 * It is a dnd-kit drop target: dropping a solid card here re-homes it to `zone`.
 */
export function FieldSection({ zone, dropId, entries, onRemove, tint }: Props) {
  const { setNodeRef, isOver } = useDroppable({ id: dropId });

  const solidCount = entries.filter((e) => e.variant === "solid").length;

  return (
    <div
      ref={setNodeRef}
      className={[
        "rounded-lg border p-2 transition-colors",
        // Reveal animation — parent stagger is handled by CSS animation-delay
        "animate-[tmplReveal_0.32s_ease_both]",
        isOver
          ? "border-accent/60 bg-accent/10 shadow-neon"
          : "border-accent/10",
      ].join(" ")}
      style={{
        background: isOver
          ? undefined
          : tint
            ? `linear-gradient(160deg, ${tint}, rgba(0,0,0,0.18))`
            : "rgba(0,0,0,0.18)",
      }}
    >
      {/* Header */}
      <div className="mb-1.5 flex items-center justify-between">
        <span className="font-display text-[9px] uppercase tracking-wider text-accent">
          {zone}
        </span>
        <span className="text-[10px] text-[#9fd0ff]/70">{solidCount}</span>
      </div>

      {/* Card pile */}
      <CardPile entries={entries} onRemove={onRemove} />
    </div>
  );
}
