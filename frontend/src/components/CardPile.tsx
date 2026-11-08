"use client";

import { useId } from "react";
import type { Card } from "@/lib/types";
import type { Zone } from "@/lib/zones";
import type { GhostKind } from "./BoardCard";
import { BoardCard } from "./BoardCard";
import { CardSurface } from "./card/CardSurface";

export interface PileEntry {
  card: Card;
  variant: "solid" | "ghost";
  ghostKind?: GhostKind;
}

interface Props {
  entries: PileEntry[];
  onRemove?: (cardId: string) => void;
  /** Accessible name for the pile's surface (e.g. the lane title). */
  label?: string;
  /**
   * Visible lane title above the pile (`.dd-lane-title`: Press Start 2P at 11 px,
   * accent only, no bevel — the count pill outranks lane chrome, §3.2). The pile is
   * then wrapped in a `.dd-lane` with a 1 px top rule.
   */
  title?: string;
  /** Lane the pile belongs to (forwarded to each card's context menu). */
  zone?: Zone;
}

/**
 * A tuck pile of cards.
 * Cards overlap (3D tuck via CSS transforms) and stay static; hovering an
 * individual card lifts just that one above the pile.
 */
export function CardPile({ entries, onRemove, label = "Pile", title, zone }: Props) {
  const surfaceId = useId();
  const pile =
    entries.length === 0 ? (
      <p className="py-2 text-xs italic text-[#9fd0ff]/50">no cards</p>
    ) : (
      <CardSurface
      id={surfaceId}
      orientation="row"
      label={label}
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
          surfaceId={surfaceId}
          zone={zone}
        />
      ))}
    </CardSurface>
    );

  if (!title) return pile;
  return (
    <div className="dd-lane">
      <p className="dd-lane-title">{title}</p>
      {pile}
    </div>
  );
}
