"use client";

import { useState, useCallback } from "react";
import { useDraggable } from "@dnd-kit/core";
import type { Card } from "@/lib/types";
import type { Zone } from "@/lib/zones";
import { CardInteractive } from "./card/CardInteractive";

export type BoardCardVariant = "solid" | "ghost";
export type GhostKind = "additional" | "bridge";

interface Props {
  card: Card;
  variant: BoardCardVariant;
  ghostKind?: GhostKind;
  /** Called when the remove button is clicked (solid cards only). */
  onRemove?: () => void;
  /** Stacking index for CSS tuck offset — 0 = front, increases into the pile. */
  stackIndex: number;
  /** Id of the enclosing `CardSurface` (the pile). */
  surfaceId: string;
  /** Lane the card sits in — checks the current entry of the "Move to …" submenu. */
  zone?: Zone;
}

const TUCK_OFFSET_X = 44; // px overlap between consecutive cards
const HOVER_LIFT_Y = -10; // px the hovered card rises above the static pile (§4.7: 10 px)
const MAX_TUCK_ROT = [0, 2.5, -2, 1.5, -1]; // rotation per position (wraps)

export function BoardCard({ card, variant, ghostKind, onRemove, stackIndex, surfaceId, zone }: Props) {
  const [hovering, setHovering] = useState(false);

  // Use a separator unlikely to appear in Scryfall UUIDs when constructing the
  // drag id, so we can reliably strip the suffix back to the card id on drop.
  // Format: "bc::<cardId>::<variant>::<stackIndex>"
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: `bc::${card.id}::${variant}::${stackIndex}`,
    // Ghosts are not independently draggable
    disabled: variant === "ghost",
  });

  const handleEnter = useCallback(() => setHovering(true), []);
  const handleLeave = useCallback(() => setHovering(false), []);

  const rot = MAX_TUCK_ROT[stackIndex % MAX_TUCK_ROT.length] ?? 0;
  // Only the hovered card lifts (and straightens) — the rest of the pile is static.
  const liftY = hovering ? HOVER_LIFT_Y : 0;
  const dragX = transform ? transform.x : 0;
  const dragY = transform ? transform.y : 0;

  const tuckStyle: React.CSSProperties = {
    position: "relative",
    marginLeft: stackIndex === 0 ? 0 : -TUCK_OFFSET_X,
    transform: `rotate(${hovering ? 0 : rot}deg) translate(${dragX}px, ${dragY + liftY}px)`,
    transition: "transform 0.12s ease",
    zIndex: hovering ? 999 : stackIndex,
    opacity: isDragging ? 0.35 : variant === "ghost" ? 0.5 : 1,
  };

  // dnd-kit's PointerSensor in page.tsx has `activationConstraint: { distance: 6 }`,
  // so a plain click never starts a drag and still reaches CardInteractive's menu.
  const dragHandle = variant === "solid" ? { ...listeners, ...attributes } : undefined;

  return (
    <CardInteractive
      ref={setNodeRef}
      card={card}
      size="pile"
      context="deck"
      surfaceId={surfaceId}
      zone={zone}
      state={{ ghost: ghostKind, dragging: isDragging }}
      dragHandle={dragHandle}
      onRemove={onRemove}
      style={tuckStyle}
      className={[
        "group flex-none select-none",
        variant === "solid" ? "cursor-grab active:cursor-grabbing" : "cursor-default",
      ].join(" ")}
      onMouseEnter={handleEnter}
      onMouseLeave={handleLeave}
    >
      {/* Ghost overlay label */}
      {variant === "ghost" && ghostKind && (
        <div
          className="pointer-events-none absolute inset-x-0 bottom-0 flex items-end justify-center
                     bg-gradient-to-t from-ink/80 to-transparent pb-1"
        >
          <span className="text-[7px] font-bold uppercase tracking-wider text-cyan">{ghostKind}</span>
        </div>
      )}

      {/* Remove button for solid cards */}
      {variant === "solid" && onRemove && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          className="absolute -right-1 -top-1 hidden h-5 w-5 items-center justify-center
                     rounded-full bg-red-600 text-xs text-white group-hover:flex"
          aria-label={`Remove ${card.name}`}
        >
          ×
        </button>
      )}
    </CardInteractive>
  );
}
