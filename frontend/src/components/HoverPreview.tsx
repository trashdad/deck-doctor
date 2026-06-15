"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { Card } from "@/lib/types";

interface Props {
  card: Card;
  /** When true the preview is mounted and follows the cursor. */
  active: boolean;
}

const PREVIEW_W = 488; // px — ~3× a normal 160px card tile (≈500% of the 70px board card)

// Track the cursor globally so the preview can position itself the instant a card
// is hovered (without waiting for the next mousemove).
const lastMouse = { x: 0, y: 0 };
if (typeof window !== "undefined") {
  window.addEventListener(
    "mousemove",
    (e) => {
      lastMouse.x = e.clientX;
      lastMouse.y = e.clientY;
    },
    { passive: true },
  );
}

/**
 * Cursor-following 2× card preview, portaled to <body> so no transformed
 * ancestor can offset its fixed position. Appears immediately on hover.
 */
export function HoverPreview({ card, active }: Props) {
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    if (!active) {
      setPos(null);
      return;
    }
    const place = (cx: number, cy: number) => {
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const PREVIEW_H = Math.round(PREVIEW_W * (680 / 488));
      let x = cx + 24;
      let y = cy - PREVIEW_H / 2;
      if (x + PREVIEW_W > vw - 8) x = cx - PREVIEW_W - 24;
      if (y < 8) y = 8;
      if (y + PREVIEW_H > vh - 8) y = vh - PREVIEW_H - 8;
      setPos({ x, y });
    };
    // Position immediately at the current cursor, then follow.
    place(lastMouse.x, lastMouse.y);
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

  const art = card.image_uris?.normal;

  return createPortal(
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
    </div>,
    document.body,
  );
}
