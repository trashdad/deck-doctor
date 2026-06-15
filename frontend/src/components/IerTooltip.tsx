"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/store/auth";
import { ierBreakdown } from "@/lib/api";

// Lifted here so it's the single source of truth shared with UserMenu.tsx
export const PATREON_URL = "https://www.patreon.com/simmander";

const TOOLTIP_W = 280; // px

// Mirror HoverPreview's global cursor tracker so we position instantly on mount.
const _lastCursor = { x: 0, y: 0 };
if (typeof window !== "undefined") {
  window.addEventListener(
    "mousemove",
    (e) => {
      _lastCursor.x = e.clientX;
      _lastCursor.y = e.clientY;
    },
    { passive: true },
  );
}

interface IerFactor {
  label: string;
  detail: string;
  value: number;
}

interface IerBreakdownResult {
  locked: boolean;
  ier: number;
  factors?: IerFactor[];
}

/** Cursor-following IER tooltip, portaled to <body>. pointer-events:none so it
 *  never steals hover from the card below. The anchor div is responsible for
 *  pointer events; this just renders the floating panel. */
export function IerTooltip({
  cardId,
  ier,
  active,
}: {
  cardId: string;
  ier: number;
  active: boolean;
}) {
  const { user } = useAuth();
  const isMythic = user?.tier === "mythic";

  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  const rafRef = useRef<number | null>(null);

  const { data } = useQuery<IerBreakdownResult>({
    queryKey: ["ier", cardId],
    queryFn: () => ierBreakdown(cardId),
    enabled: active && isMythic,
    staleTime: 5 * 60 * 1000,
  });

  useEffect(() => {
    if (!active) {
      setPos(null);
      return;
    }
    const place = (cx: number, cy: number) => {
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const h = 300; // estimated tooltip height
      let x = cx + 16;
      let y = cy - h / 2;
      if (x + TOOLTIP_W > vw - 8) x = cx - TOOLTIP_W - 16;
      if (y < 8) y = 8;
      if (y + h > vh - 8) y = vh - h - 8;
      setPos({ x, y });
    };

    // Seed position immediately from current cursor.
    place(_lastCursor.x, _lastCursor.y);

    const onMove = (e: MouseEvent) => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(() => {
        place(e.clientX, e.clientY);
        rafRef.current = null;
      });
    };
    window.addEventListener("mousemove", onMove);
    return () => {
      window.removeEventListener("mousemove", onMove);
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, [active]);

  if (!active || !pos || typeof document === "undefined") return null;

  return createPortal(
    <div
      className="pointer-events-none fixed z-[400] w-[280px] rounded-lg border border-accent/40
                 bg-[#1a1628] shadow-[0_8px_32px_rgba(0,0,0,0.8)] text-xs"
      style={{ left: pos.x, top: pos.y }}
    >
      {/* Header */}
      <div className="border-b border-accent/30 px-3 py-2">
        <p className="font-bold text-accent tracking-wide">Isolated Efficiency Rating</p>
        <p className="mt-0.5 text-zinc-400 leading-snug">
          A transparent heuristic scoring a card's raw value in a vacuum — mana
          efficiency, card advantage, and body stats, on a 1–20 scale.
        </p>
      </div>

      {isMythic && data && !data.locked ? (
        /* Mythic — real factor breakdown */
        <div className="px-3 py-2 space-y-1">
          {data.factors?.map((f, i) => (
            <div key={i} className="flex items-baseline justify-between gap-2">
              <div className="min-w-0">
                <span className="font-semibold text-zinc-200">{f.label}</span>
                <span className="ml-1.5 text-zinc-500">{f.detail}</span>
              </div>
              <span
                className={`shrink-0 font-mono font-semibold ${
                  f.value >= 0 ? "text-emerald-400" : "text-red-400"
                }`}
              >
                {f.value >= 0 ? "+" : ""}
                {f.value.toFixed(2)}
              </span>
            </div>
          ))}
          <div className="mt-1.5 flex items-center justify-between border-t border-accent/20 pt-1.5">
            <span className="font-bold text-zinc-100">Total IER</span>
            <span className="font-mono font-bold text-accent text-sm">{ier}</span>
          </div>
        </div>
      ) : (
        /* Free / anonymous — fuzzy teaser */
        <div className="px-3 py-2 space-y-1">
          {/* Blurred placeholder rows */}
          {[
            { label: "Base", value: "+6.00" },
            { label: "Mana efficiency", value: "+?.??" },
            { label: "Card advantage", value: "+?.??" },
          ].map((row, i) => (
            <div key={i} className="flex items-baseline justify-between gap-2">
              <span className={`font-semibold ${i === 0 ? "text-zinc-200" : "blur-[3px] select-none text-zinc-200"}`}>
                {i === 0 ? row.label : row.label}
              </span>
              <span
                className={`font-mono font-semibold text-emerald-400 ${i === 0 ? "" : "blur-[3px] select-none"}`}
              >
                {row.value}
              </span>
            </div>
          ))}
          <div className="mt-1.5 flex items-center justify-between border-t border-accent/20 pt-1.5">
            <span className="font-bold text-zinc-100">Total IER</span>
            <span className="font-mono font-bold text-accent text-sm">{ier}</span>
          </div>
          {/* CTA */}
          <a
            href={PATREON_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="pointer-events-auto mt-2 block rounded-md bg-accent/15 border border-accent/40
                       px-2 py-1.5 text-center text-[11px] font-semibold text-accent
                       hover:bg-accent/25 transition"
          >
            ★ Reveal the full calculation — go Mythic on Patreon
          </a>
        </div>
      )}
    </div>,
    document.body,
  );
}
