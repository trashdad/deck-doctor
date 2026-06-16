"use client";

import { useState, useCallback } from "react";
import { useDraggable, useDroppable } from "@dnd-kit/core";
import type { BasicEntry, DeckCard } from "@/store/deck";
import type { Card } from "@/lib/types";
import type { Zone } from "@/lib/zones";
import { CardTile } from "./CardTile";
import { CardMenu } from "./CardMenu";

function BasicsRow({
  basics,
  onSetBasic,
}: {
  basics: Record<string, BasicEntry>;
  onSetBasic: (id: string, qty: number, card?: Card) => void;
}) {
  const entries = Object.entries(basics);
  if (entries.length === 0) return null;
  return (
    <div className="col-span-full mt-1 space-y-1 border-t border-accent/15 pt-2">
      {entries.map(([id, b]) => (
        <div key={id} className="flex items-center justify-between gap-2 text-xs">
          <span className="truncate text-[#c8b6ff]">{b.card.name}</span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => onSetBasic(id, b.quantity - 1)}
              className="h-5 w-5 rounded border border-accent/30 bg-accent/5 text-accent hover:bg-accent/15"
            >
              −
            </button>
            <span className="w-6 text-center font-semibold text-accent">×{b.quantity}</span>
            <button
              onClick={() => onSetBasic(id, b.quantity + 1, b.card)}
              className="h-5 w-5 rounded border border-accent/30 bg-accent/5 text-accent hover:bg-accent/15"
            >
              +
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

function DraggableCard({
  dc,
  onRemove,
}: {
  dc: DeckCard;
  onRemove: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, isDragging } =
    useDraggable({ id: dc.card.id });

  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null);

  const style = transform
    ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)`, zIndex: 50 }
    : undefined;

  const handleClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setMenu({ x: e.clientX, y: e.clientY });
  }, []);

  return (
    <>
      <div
        ref={setNodeRef}
        style={{ ...style, opacity: isDragging ? 0.4 : 1 }}
        className="group relative"
        {...listeners}
        {...attributes}
        onClick={handleClick}
      >
        <CardTile card={dc.card} compact />
        {/* Quick-remove on hover — also available via the click menu */}
        <button
          onClick={(e) => { e.stopPropagation(); onRemove(); }}
          className="absolute -right-1 -top-1 hidden h-5 w-5 items-center justify-center
                     rounded-full bg-red-600 text-xs text-white group-hover:flex"
          aria-label="remove"
        >
          ×
        </button>
      </div>

      {menu && (
        <CardMenu
          card={dc.card}
          anchor={menu}
          onRemove={onRemove}
          onClose={() => setMenu(null)}
        />
      )}
    </>
  );
}

export function ZoneColumn({
  zone,
  cards,
  onRemove,
  basics,
  onSetBasic,
}: {
  zone: Zone;
  cards: DeckCard[];
  onRemove: (id: string) => void;
  basics?: Record<string, BasicEntry>;
  onSetBasic?: (id: string, qty: number, card?: Card) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: zone });
  const subtotalIer = cards.reduce((s, c) => s + (c.card.ier ?? 0), 0);
  const basicCount = basics ? Object.values(basics).reduce((s, b) => s + b.quantity, 0) : 0;

  return (
    <div
      ref={setNodeRef}
      className={`flex min-h-[140px] flex-col rounded-lg border p-2 backdrop-blur-sm transition-colors ${
        isOver ? "border-accent/60 bg-panel2/80 shadow-neon" : "border-accent/20 bg-panel/80"
      }`}
    >
      <div className="mb-2 flex items-center justify-between px-1">
        <h3 className="arcade-bevel text-sm tracking-wide">
          {zone}
        </h3>
        <span className="text-xs text-[#9fd0ff]/70">
          {cards.length + basicCount}
          {subtotalIer > 0 && (
            <span className="ml-2 text-cyan">Σ{subtotalIer.toFixed(0)}</span>
          )}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
        {cards.map((dc) => (
          <DraggableCard
            key={dc.card.id}
            dc={dc}
            onRemove={() => onRemove(dc.card.id)}
          />
        ))}
        {cards.length === 0 && basicCount === 0 && (
          <p className="col-span-full py-3 text-center text-xs text-[#9fd0ff]/50">
            drag cards here
          </p>
        )}
        {basics && onSetBasic && <BasicsRow basics={basics} onSetBasic={onSetBasic} />}
      </div>
    </div>
  );
}
