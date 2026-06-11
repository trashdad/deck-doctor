"use client";

import { useEffect, useRef, useState } from "react";
import type { Card } from "@/lib/types";

interface Props {
  card: Card;
  /** When true the preview is mounted and follows the cursor. */
  active: boolean;
}

const PREVIEW_W = 220; // px — ~250% of the 70px board card

/**
 * Cursor-following 250% card preview.
 * Mount it (active=true) while the parent card is hovered; it attaches
 * a mousemove listener and follows the pointer offset from the cursor.
 */
export function HoverPreview({ card, active }: Props) {
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    if (!active) {
      setPos(null);
      return;
    }
    const onMove = (e: MouseEvent) => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(() => {
        const vw = window.innerWidth;
        const vh = window.innerHeight;
        const PREVIEW_H = Math.round(PREVIEW_W * (680 / 488));
        let x = e.clientX + 16;
        let y = e.clientY - PREVIEW_H / 2;
        if (x + PREVIEW_W > vw - 8) x = e.clientX - PREVIEW_W - 16;
        if (y < 8) y = 8;
        if (y + PREVIEW_H > vh - 8) y = vh - PREVIEW_H - 8;
        setPos({ x, y });
        rafRef.current = null;
      });
    };
    window.addEventListener("mousemove", onMove);
    return () => {
      window.removeEventListener("mousemove", onMove);
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, [active]);

  if (!active || !pos) return null;

  const art = card.image_uris?.normal;

  return (
    <div
      className="pointer-events-none fixed z-[300] overflow-hidden rounded-[4.75%/3.4%]
                 shadow-[0_0_0_1px_rgba(201,162,39,0.6),_0_16px_48px_rgba(0,0,0,0.8)]"
      style={{ left: pos.x, top: pos.y, width: PREVIEW_W }}
    >
      {art ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={art}
          alt={card.name}
          style={{ width: "100%", display: "block" }}
          loading="eager"
        />
      ) : (
        <div
          className="flex flex-col justify-between bg-gradient-to-br from-[#221d33] to-[#14111f] p-3 text-xs"
          style={{ width: PREVIEW_W, height: Math.round(PREVIEW_W * (680 / 488)) }}
        >
          <span className="font-semibold text-zinc-100">{card.name}</span>
          <span className="text-zinc-400">{card.type_line}</span>
          <span className="line-clamp-6 text-zinc-500">{card.oracle_text}</span>
          <span className="text-zinc-400">{card.color_identity.join("") || "C"}</span>
        </div>
      )}
    </div>
  );
}
