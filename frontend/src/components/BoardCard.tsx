"use client";

import { useState, useCallback } from "react";
import { useDraggable } from "@dnd-kit/core";
import type { Card } from "@/lib/types";
import { HoverPreview } from "./HoverPreview";

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
}

const TUCK_OFFSET_X = 44; // px overlap between consecutive cards
const HOVER_LIFT_Y = -18; // px the hovered card rises above the static pile
const MAX_TUCK_ROT = [0, 2.5, -2, 1.5, -1]; // rotation per position (wraps)

export function BoardCard({
  card,
  variant,
  ghostKind,
  onRemove,
  stackIndex,
}: Props) {
  const [hovering, setHovering] = useState(false);

  // Use a separator unlikely to appear in Scryfall UUIDs when constructing the
  // drag id, so we can reliably strip the suffix back to the card id on drop.
  // Format: "bc::<cardId>::<variant>::<stackIndex>"
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: `bc::${card.id}::${variant}::${stackIndex}`,
    // Ghosts are not independently draggable
    disabled: variant === "ghost",
  });

  const handleMouseEnter = useCallback(() => setHovering(true), []);
  const handleMouseLeave = useCallback(() => setHovering(false), []);

  const rot = MAX_TUCK_ROT[stackIndex % MAX_TUCK_ROT.length] ?? 0;
  // Only the hovered card lifts (and straightens) — the rest of the pile is static.
  const liftY = hovering ? HOVER_LIFT_Y : 0;
  // Drag override
  const dragX = transform ? transform.x : 0;
  const dragY = transform ? transform.y : 0;

  const tuckStyle: React.CSSProperties = {
    position: "relative",
    // Overlap cards like a tucked pile
    marginLeft: stackIndex === 0 ? 0 : -TUCK_OFFSET_X,
    transform: `rotate(${hovering ? 0 : rot}deg) translate(${dragX}px, ${dragY + liftY}px)`,
    transition: "transform 0.12s ease",
    // Hovered card floats above the pile; otherwise later cards sit atop earlier ones.
    zIndex: hovering ? 999 : stackIndex,
    opacity: isDragging ? 0.35 : variant === "ghost" ? 0.5 : 1,
  };

  const art = card.image_uris?.normal;

  return (
    <>
      <div
        ref={setNodeRef}
        style={tuckStyle}
        className={[
          "mtg-card group flex-none cursor-pointer select-none",
          "w-[70px]", // fixed width inside pile
          variant === "ghost"
            ? "border border-dashed border-amber-500/70"
            : "",
          variant === "solid" ? "cursor-grab active:cursor-grabbing" : "cursor-default",
        ]
          .filter(Boolean)
          .join(" ")}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        {...(variant === "solid" ? { ...listeners, ...attributes } : {})}
        data-card-hover="1"
      >
        {art ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={art} alt={card.name} loading="lazy" />
        ) : (
          <div className="mtg-fallback">
            <div className="flex items-start justify-between gap-1">
              <span className="font-semibold text-zinc-100 text-[8px]">{card.name}</span>
            </div>
            <div className="text-zinc-400 text-[7px]">{card.type_line}</div>
          </div>
        )}

        {/* Ghost overlay label */}
        {variant === "ghost" && ghostKind && (
          <div
            className="pointer-events-none absolute inset-x-0 bottom-0 flex items-end justify-center
                       bg-gradient-to-t from-black/70 to-transparent pb-1"
          >
            <span className="text-[7px] font-bold uppercase tracking-wider text-amber-300">
              {ghostKind}
            </span>
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
      </div>

      {/* 250% cursor-following hover preview */}
      <HoverPreview card={card} active={hovering} />
    </>
  );
}
