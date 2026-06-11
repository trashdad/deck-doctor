"use client";

import type { Card } from "@/lib/types";
import type { GhostKind } from "./BoardCard";
import { BoardCard } from "./BoardCard";

export interface PileEntry {
  card: Card;
  variant: "solid" | "ghost";
  ghostKind?: GhostKind;
}

interface Props {
  entries: PileEntry[];
  onRemove?: (cardId: string) => void;
}

/**
 * A tuck pile of cards.
 * Cards overlap (3D tuck via CSS transforms) and stay static; hovering an
 * individual card lifts just that one above the pile.
 */
export function CardPile({ entries, onRemove }: Props) {
  if (entries.length === 0) {
    return (
      <p className="py-2 text-xs italic text-zinc-600">no cards</p>
    );
  }

  return (
    <div
      className="relative flex min-h-[100px] items-start py-1"
      style={{
        // Reserve horizontal space for the pile
        minWidth:
          entries.length === 1
            ? 70
            : Math.min(70 + (entries.length - 1) * (70 - 44), 300),
      }}
    >
      {entries.map((entry, i) => (
        <BoardCard
          key={`${entry.card.id}-${entry.variant}-${i}`}
          card={entry.card}
          variant={entry.variant}
          ghostKind={entry.ghostKind}
          onRemove={entry.variant === "solid" && onRemove ? () => onRemove(entry.card.id) : undefined}
          stackIndex={i}
        />
      ))}
    </div>
  );
}
