"use client";

import { useDraggable, useDroppable } from "@dnd-kit/core";
import type { DeckCard } from "@/store/deck";
import type { Zone } from "@/lib/zones";
import { CardTile } from "./CardTile";

function DraggableCard({ dc, onRemove }: { dc: DeckCard; onRemove: () => void }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } =
    useDraggable({ id: dc.card.id });
  const style = transform
    ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)`, zIndex: 50 }
    : undefined;
  return (
    <div
      ref={setNodeRef}
      style={{ ...style, opacity: isDragging ? 0.4 : 1 }}
      className="group relative"
      {...listeners}
      {...attributes}
    >
      <CardTile card={dc.card} compact />
      <button
        onClick={(e) => {
          e.stopPropagation();
          onRemove();
        }}
        className="absolute -right-1 -top-1 hidden h-5 w-5 rounded-full bg-red-600 text-xs
                   leading-5 text-white group-hover:block"
        aria-label="remove"
      >
        ×
      </button>
    </div>
  );
}

export function ZoneColumn({
  zone,
  cards,
  onRemove,
}: {
  zone: Zone;
  cards: DeckCard[];
  onRemove: (id: string) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: zone });
  const subtotalIer = cards.reduce((s, c) => s + (c.card.ier ?? 0), 0);

  return (
    <div
      ref={setNodeRef}
      className={`flex min-h-[140px] flex-col rounded-lg border p-2 transition-colors ${
        isOver ? "border-accent bg-panel2" : "border-edge bg-panel"
      }`}
    >
      <div className="mb-2 flex items-center justify-between px-1">
        <h3 className="font-display text-sm font-semibold tracking-wide text-zinc-100">
          {zone}
        </h3>
        <span className="text-xs text-zinc-500">
          {cards.length}
          {subtotalIer > 0 && (
            <span className="ml-2 text-accent">Σ{subtotalIer.toFixed(0)}</span>
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
        {cards.length === 0 && (
          <p className="col-span-full py-3 text-center text-xs text-zinc-600">
            drag cards here
          </p>
        )}
      </div>
    </div>
  );
}
