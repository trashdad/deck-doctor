"use client";

import { useState } from "react";
import type { Card } from "@/lib/types";
import { HoverPreview } from "./HoverPreview";

interface Props {
  commander: Card | null;
  onRemove?: () => void;
}

function CommanderCard({ card, onRemove }: { card: Card; onRemove?: () => void }) {
  const [hovering, setHovering] = useState(false);
  const art = card.image_uris?.normal;

  return (
    <>
      <div
        className="group relative flex-none cursor-pointer"
        onMouseEnter={() => setHovering(true)}
        onMouseLeave={() => setHovering(false)}
        data-card-hover="1"
      >
        <div
          className="mtg-card w-[80px] shadow-[0_0_0_1px_rgba(201,162,39,0.5),_0_8px_24px_rgba(0,0,0,0.6)]"
        >
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

        {onRemove && (
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

      <HoverPreview card={card} active={hovering} />
    </>
  );
}

/**
 * The gilded strip above the board showing the commander(s).
 * Always rendered; shows an empty-state prompt when no commander is in the deck.
 */
export function CommanderStrip({ commander, onRemove }: Props) {
  return (
    <div
      className="mb-3 flex items-center gap-4 rounded-xl border border-accent/50 px-4 py-3"
      style={{
        background: "linear-gradient(180deg, rgba(201,162,39,0.10), rgba(201,162,39,0.03))",
      }}
      data-testid="commander-strip"
    >
      <span className="font-display shrink-0 text-sm font-semibold tracking-wide text-accent">
        Commander
      </span>

      {commander ? (
        <div className="flex items-center gap-3">
          <CommanderCard card={commander} onRemove={onRemove} />
          <div className="flex flex-col gap-0.5">
            <span className="text-sm font-semibold text-zinc-100">{commander.name}</span>
            <span className="text-xs italic text-zinc-500">{commander.type_line}</span>
            {commander.color_identity.length > 0 && (
              <div className="flex gap-0.5 pt-0.5">
                {commander.color_identity.map((c) => (
                  <span
                    key={c}
                    className="flex h-4 w-4 items-center justify-center rounded-full text-[9px] font-bold"
                    style={{
                      background:
                        c === "W"
                          ? "#f8f5e3"
                          : c === "U"
                            ? "#3b82f6"
                            : c === "B"
                              ? "#5b4a63"
                              : c === "R"
                                ? "#ef4444"
                                : c === "G"
                                  ? "#22c55e"
                                  : "#9aa0a6",
                      color: "#0c0a14",
                    }}
                  >
                    {c}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      ) : (
        <p className="text-sm italic text-zinc-600">
          Search for a Legendary Creature to set your commander
        </p>
      )}
    </div>
  );
}
