"use client";

import type { ReactNode } from "react";
import type { Card } from "@/lib/types";
import { canHavePartner } from "@/lib/partners";
import { useUI } from "@/store/ui";
import { CardInteractive } from "./card/CardInteractive";
import { CardSurface } from "./card/CardSurface";

const COMMANDER_SURFACE = "commander";

interface Props {
  /** All cards currently in the Commanders zone (1 = commander, 2 = partner pair). */
  commanders: Card[];
  onRemove: (id: string) => void;
  /** Deck-action controls stacked on the right of the pane (template/doctor/etc). */
  controls?: ReactNode;
}

const PIP_BG: Record<string, string> = {
  W: "#f8f5e3",
  U: "#3b82f6",
  B: "#5b4a63",
  R: "#ef4444",
  G: "#22c55e",
};

function CommanderCard({ card, onRemove }: { card: Card; onRemove: () => void }) {
  return (
    <>
      <div className="flex items-center gap-2">
        <CardInteractive
          card={card}
          size="pile"
          context="commander"
          surfaceId={COMMANDER_SURFACE}
          onRemove={onRemove}
          loading="eager"
          className="group flex-none shadow-[0_0_0_1px_rgba(255,210,74,0.55),_0_0_18px_rgba(255,43,214,0.4),_0_8px_24px_rgba(0,0,0,0.6)]"
        >
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
        </CardInteractive>
        <div className="flex min-w-0 flex-col gap-0.5">
          <span className="truncate text-sm font-semibold text-white [text-shadow:0_0_14px_rgba(255,43,214,0.45)]">
            {card.name}
          </span>
          <span className="truncate text-xs italic text-[#c8b6ff]">{card.type_line}</span>
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
    </>
  );
}

/**
 * The gilded strip above the board showing the commander(s).
 * Always rendered; supports a partner pair and a clear remove + add-partner.
 */
export function CommanderStrip({ commanders, onRemove, controls }: Props) {
  const setSearchTab = useUI((s) => s.setSearchTab);
  const setPartnerPick = useUI((s) => s.setPartnerPick);
  // Only offer a partner when the lone commander actually has a partner ability.
  const canPartner = commanders.length === 1 && canHavePartner(commanders[0]);

  return (
    <div
      className="mb-3 flex flex-wrap items-center gap-4 rounded-xl border border-accent px-4 py-3 shadow-neon backdrop-blur-sm"
      style={{ background: "linear-gradient(110deg, rgba(255,43,214,0.12), rgba(255,170,0,0.10))" }}
      data-testid="commander-strip"
    >
      <span className="arcade-bevel shrink-0 text-sm tracking-wide">
        Commander{commanders.length > 1 ? "s" : ""}
      </span>

      {commanders.length === 0 ? (
        <p className="text-sm italic text-[#c8b6ff]/70">
          Pick a Legendary Creature from the commander list to set your commander
        </p>
      ) : (
        <>
          <CardSurface
            id={COMMANDER_SURFACE}
            orientation="row"
            label="Commanders"
            className="flex flex-wrap items-center gap-4"
          >
            {commanders.map((c) => (
              <CommanderCard key={c.id} card={c} onRemove={() => onRemove(c.id)} />
            ))}
          </CardSurface>
          {/* A partner pair is at most 2 commanders, and only if the commander
              actually has a partner ability. */}
          {canPartner && (
            <button
              onClick={() => {
                setPartnerPick(true);
                setSearchTab("commanders");
              }}
              data-testid="add-partner"
              title="Add a valid partner commander"
              className="flex h-[88px] w-[72px] flex-none flex-col items-center justify-center gap-1
                         rounded-md border border-dashed border-cyan/60 text-cyan
                         transition hover:bg-cyan/15 hover:shadow-neon"
            >
              <span className="text-xl leading-none">＋</span>
              <span className="px-1 text-center text-[9px] font-semibold uppercase tracking-wider">
                Add partner
              </span>
            </button>
          )}
        </>
      )}

      {controls && <div className="ml-auto flex-none">{controls}</div>}
    </div>
  );
}
