"use client";

import { useState } from "react";
import type { Card } from "@/lib/types";
import { useUI } from "@/store/ui";
import { HoverPreview } from "./HoverPreview";

interface Props {
  /** All cards currently in the Commanders zone (1 = commander, 2 = partner pair). */
  commanders: Card[];
  onRemove: (id: string) => void;
}

const PIP_BG: Record<string, string> = {
  W: "#f8f5e3",
  U: "#3b82f6",
  B: "#5b4a63",
  R: "#ef4444",
  G: "#22c55e",
};

function CommanderCard({ card, onRemove }: { card: Card; onRemove: () => void }) {
  const [hovering, setHovering] = useState(false);
  const art = card.image_uris?.normal;

  return (
    <>
      <div className="flex items-center gap-2">
        <div
          className="group relative flex-none cursor-pointer"
          onMouseEnter={() => setHovering(true)}
          onMouseLeave={() => setHovering(false)}
          data-card-hover="1"
        >
          <div className="mtg-card w-[72px] shadow-[0_0_0_1px_rgba(201,162,39,0.5),_0_8px_24px_rgba(0,0,0,0.6)]">
            {art ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={art} alt={card.name} loading="eager" />
            ) : (
              <div className="mtg-fallback">
                <span className="font-semibold text-zinc-100 text-[8px]">{card.name}</span>
                <span className="text-zinc-400 text-[7px]">{card.type_line}</span>
              </div>
            )}
          </div>
          {/* Always-visible remove handle. */}
          <button
            onClick={(e) => {
              e.stopPropagation();
              onRemove();
            }}
            data-testid="remove-commander"
            title={`Remove ${card.name}`}
            aria-label={`Remove ${card.name}`}
            className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center
                       rounded-full border border-red-300/40 bg-red-600 text-xs font-bold text-white
                       shadow transition hover:bg-red-500"
          >
            ×
          </button>
        </div>
        <div className="flex min-w-0 flex-col gap-0.5">
          <span className="truncate text-sm font-semibold text-zinc-100">{card.name}</span>
          <span className="truncate text-xs italic text-zinc-500">{card.type_line}</span>
          {card.color_identity.length > 0 && (
            <div className="flex gap-0.5 pt-0.5">
              {card.color_identity.map((c) => (
                <span
                  key={c}
                  className="flex h-4 w-4 items-center justify-center rounded-full text-[9px] font-bold"
                  style={{ background: PIP_BG[c] ?? "#9aa0a6", color: "#0c0a14" }}
                >
                  {c}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
      <HoverPreview card={card} active={hovering} />
    </>
  );
}

/**
 * The gilded strip above the board showing the commander(s).
 * Always rendered; supports a partner pair and a clear remove + add-partner.
 */
export function CommanderStrip({ commanders, onRemove }: Props) {
  const setSearchTab = useUI((s) => s.setSearchTab);

  return (
    <div
      className="mb-3 flex flex-wrap items-center gap-4 rounded-xl border border-accent/50 px-4 py-3"
      style={{ background: "linear-gradient(180deg, rgba(201,162,39,0.10), rgba(201,162,39,0.03))" }}
      data-testid="commander-strip"
    >
      <span className="font-display shrink-0 text-sm font-semibold tracking-wide text-accent">
        Commander{commanders.length > 1 ? "s" : ""}
      </span>

      {commanders.length === 0 ? (
        <p className="text-sm italic text-zinc-600">
          Pick a Legendary Creature from the commander list to set your commander
        </p>
      ) : (
        <>
          {commanders.map((c) => (
            <CommanderCard key={c.id} card={c} onRemove={() => onRemove(c.id)} />
          ))}
          {/* A partner pair is at most 2 commanders. */}
          {commanders.length < 2 && (
            <button
              onClick={() => setSearchTab("commanders")}
              data-testid="add-partner"
              title="Add a second (partner) commander"
              className="flex h-[88px] w-[72px] flex-none flex-col items-center justify-center gap-1
                         rounded-md border border-dashed border-accent/50 text-accent/80
                         transition hover:border-accent hover:bg-accent/10"
            >
              <span className="text-xl leading-none">＋</span>
              <span className="px-1 text-center text-[9px] font-semibold uppercase tracking-wider">
                Add partner
              </span>
            </button>
          )}
        </>
      )}
    </div>
  );
}
