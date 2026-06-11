"use client";

import { useState } from "react";
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
 * A fan/tuck pile of cards.
 * Cards overlap (3D tuck via CSS transforms); hovering the pile fans them
 * so tucked cards become visible.
 */
export function CardPile({ entries, onRemove }: Props) {
  const [fanned, setFanned] = useState(false);

  if (entries.length === 0) {
    return (
      <p className="py-2 text-xs italic text-zinc-600">no cards</p>
    );
  }

  return (
    <div
      className="relative flex min-h-[100px] cursor-pointer items-start py-1"
      style={{
        // Reserve horizontal space for the pile
        minWidth:
          entries.length === 1
            ? 70
            : Math.min(70 + (entries.length - 1) * (70 - 44), 300),
      }}
      onMouseEnter={() => setFanned(true)}
      onMouseLeave={() => setFanned(false)}
    >
      {entries.map((entry, i) => (
        <BoardCard
          key={`${entry.card.id}-${entry.variant}-${i}`}
          card={entry.card}
          variant={entry.variant}
          ghostKind={entry.ghostKind}
          onRemove={entry.variant === "solid" && onRemove ? () => onRemove(entry.card.id) : undefined}
          stackIndex={i}
          stackSize={entries.length}
          fanned={fanned}
        />
      ))}
    </div>
  );
}
