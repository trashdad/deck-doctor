"use client";

import { useEffect, useRef } from "react";
import { useOracle } from "@/store/oracle";
import { OracleTextRenderer } from "./OracleTextRenderer";

const PIP_COLORS: Record<string, string> = {
  W: "#f8f5e3", U: "#3b82f6", B: "#a78bbd", R: "#ef4444", G: "#22c55e", C: "#9aa0a6",
};

/** Floating card detail that appears when hovering a card tile. */
export function CardHoverDetail() {
  const { hoveredCard, hoverAnchor, setHover } = useOracle((s) => ({
    hoveredCard: s.hoveredCard,
    hoverAnchor: s.hoverAnchor,
    setHover: s.setHover,
  }));
  const ref = useRef<HTMLDivElement>(null);

  // Dismiss if user moves cursor away from both the card and this panel
  useEffect(() => {
    if (!hoveredCard) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && ref.current.contains(e.target as Node)) return;
      // Check if pointer is still over the card — if not, hide
      const over = document.elementFromPoint(e.clientX, e.clientY);
      if (over?.closest("[data-card-hover]")) return;
      setHover(null);
    };
    document.addEventListener("mousemove", handler);
    return () => document.removeEventListener("mousemove", handler);
  }, [hoveredCard, setHover]);

  if (!hoveredCard || !hoverAnchor) return null;

  const card = hoveredCard;
  const W = 248;
  const viewW = typeof window !== "undefined" ? window.innerWidth : 1200;
  const left =
    hoverAnchor.side === "right"
      ? Math.min(hoverAnchor.x + 8, viewW - W - 8)
      : Math.max(hoverAnchor.x - W - 8, 8);
  const top = Math.max(8, Math.min(hoverAnchor.y - 60, window.innerHeight - 400));

  return (
    <div
      ref={ref}
      className="pointer-events-auto fixed z-[200] flex flex-col gap-1 rounded-lg border border-edge
                 bg-panel/98 p-3 shadow-2xl backdrop-blur-sm"
      style={{ width: W, left, top }}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <span className="text-xs font-semibold leading-tight text-zinc-100">{card.name}</span>
        {card.ier != null && (
          <span className="shrink-0 rounded bg-accent/20 px-1 text-[10px] text-accent">
            IER {card.ier}
          </span>
        )}
      </div>

      {/* Mana pips */}
      {card.color_identity.length > 0 && (
        <div className="flex gap-0.5">
          {card.color_identity.map((c) => (
            <span
              key={c}
              className="flex h-4 w-4 items-center justify-center rounded-full text-[9px] font-bold"
              style={{ background: PIP_COLORS[c] ?? "#444", color: "#0c0a14" }}
            >
              {c}
            </span>
          ))}
        </div>
      )}

      {/* Type line */}
      <p className="text-[10px] italic text-zinc-400">{card.type_line}</p>

      {/* Oracle text — clickable phrases */}
      {card.oracle_text ? (
        <>
          <div className="my-0.5 border-t border-edge" />
          <p className="mb-0.5 text-[9px] uppercase tracking-widest text-zinc-600">
            Click a line to find similar cards
          </p>
          <OracleTextRenderer text={card.oracle_text} />
        </>
      ) : null}

      {/* Power/Toughness */}
      {card.power != null && (
        <p className="mt-0.5 text-right text-[10px] text-zinc-400">
          {card.power}/{card.toughness}
        </p>
      )}
    </div>
  );
}
