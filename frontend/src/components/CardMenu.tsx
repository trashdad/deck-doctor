"use client";

import { useEffect, useRef } from "react";
import type { Card } from "@/lib/types";
import { useSemanticStore } from "@/store/semantic";
import { useRelationshipStore } from "@/store/relationship";
import { amazonCardUrl, manapoolCardUrl, tcgplayerCardUrl } from "@/lib/affiliate";

interface CardMenuProps {
  card: Card;
  anchor: { x: number; y: number };
  onRemove?: () => void;
  onClose: () => void;
}

export function CardMenu({ card, anchor, onRemove, onClose }: CardMenuProps) {
  const openCard = useSemanticStore((s) => s.openCard);
  const openExplorer = useRelationshipStore((s) => s.open);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const down = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", down);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("mousedown", down);
      document.removeEventListener("keydown", key);
    };
  }, [onClose]);

  const W = 220;
  const maxLeft = typeof window !== "undefined" ? window.innerWidth - W - 8 : 9999;
  const maxTop = typeof window !== "undefined" ? window.innerHeight - 360 : 9999;
  const left = Math.min(anchor.x, maxLeft);
  const top = Math.min(anchor.y, maxTop);

  return (
    <div
      ref={ref}
      className="fixed z-[150] overflow-hidden rounded-lg border border-edge bg-panel
                 shadow-2xl backdrop-blur-sm"
      style={{ width: W, left, top }}
    >
      <div className="border-b border-edge px-3 py-2">
        <p className="truncate text-[10px] font-semibold uppercase tracking-widest text-accent">
          {card.name}
        </p>
        {card.ier != null && (
          <p className="text-[9px] text-zinc-500">IER {card.ier}</p>
        )}
      </div>

      <div className="py-1">
        <button
          onClick={() => {
            openExplorer(card, "similar");
            onClose();
          }}
          className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-xs
                     font-semibold tracking-wide text-zinc-200 transition
                     hover:bg-accent/10 hover:text-accent"
        >
          <span className="text-accent opacity-80">◈</span>
          SIMILAR CARDS
        </button>

        <button
          onClick={() => {
            openExplorer(card, "synergy");
            onClose();
          }}
          className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-xs
                     font-semibold tracking-wide text-zinc-200 transition
                     hover:bg-accent/10 hover:text-accent"
        >
          <span className="text-accent opacity-80">⚡</span>
          SYNERGIZES WITH
        </button>

        <button
          onClick={() => {
            openExplorer(card, "cooccurrence");
            onClose();
          }}
          className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-xs
                     font-semibold tracking-wide text-zinc-200 transition
                     hover:bg-accent/10 hover:text-accent"
        >
          <span className="text-accent opacity-80">◫</span>
          PLAYED WITH
        </button>

        <button
          onClick={() => {
            openExplorer(card, "combos");
            onClose();
          }}
          className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-xs
                     font-semibold tracking-wide text-zinc-200 transition
                     hover:bg-accent/10 hover:text-accent"
        >
          <span className="text-accent opacity-80">⬡</span>
          COMBOS &amp; ENGINES
        </button>

        <button
          onClick={() => {
            openCard(card);
            onClose();
          }}
          className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-xs
                     font-semibold tracking-wide text-zinc-400 transition
                     hover:bg-accent/5 hover:text-zinc-200"
        >
          <span className="opacity-60">⊕</span>
          FIND BY TAGS
        </button>

        {onRemove && (
          <button
            onClick={() => {
              onRemove();
              onClose();
            }}
            className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-xs
                       font-semibold tracking-wide text-red-400 transition
                       hover:bg-red-500/10"
          >
            <span className="opacity-70">✕</span>
            REMOVE FROM DECK
          </button>
        )}

        {/* Buy links */}
        <div className="mx-3 my-1 border-t border-edge" />
        <div className="flex gap-1 px-3 pb-2 pt-1">
          <a
            href={manapoolCardUrl(card.name)}
            target="_blank"
            rel="noopener noreferrer"
            className="flex flex-1 items-center justify-center gap-1 rounded border
                       border-accent/40 px-2 py-1.5 text-[10px] font-semibold
                       uppercase tracking-wide text-accent transition
                       hover:bg-accent/15 hover:border-accent/70"
          >
            ManaPool ↗
          </a>
          <a
            href={tcgplayerCardUrl(card.name)}
            target="_blank"
            rel="noopener noreferrer"
            className="flex flex-1 items-center justify-center gap-1 rounded border
                       border-zinc-600 px-2 py-1.5 text-[10px] font-semibold
                       uppercase tracking-wide text-zinc-400 transition
                       hover:border-accent/50 hover:text-accent"
          >
            TCGplayer ↗
          </a>
          <a
            href={amazonCardUrl(card.name)}
            target="_blank"
            rel="noopener noreferrer"
            className="flex flex-1 items-center justify-center gap-1 rounded border
                       border-zinc-600 px-2 py-1.5 text-[10px] font-semibold
                       uppercase tracking-wide text-zinc-400 transition
                       hover:border-accent/50 hover:text-accent"
          >
            Amazon ↗
          </a>
        </div>
      </div>
    </div>
  );
}
