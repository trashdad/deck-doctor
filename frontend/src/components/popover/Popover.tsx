"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

export interface PopoverProps extends React.HTMLAttributes<HTMLDivElement> {
  open: boolean;
  x: number;
  y: number;
  width?: number;
  height?: number;
  zIndex: number;
  /** Lets the preview translate 2 px toward its anchor (CSS keyed on data-side). */
  side?: string;
  pointerEvents?: "none" | "auto";
  children: React.ReactNode;
}

/** Mount at opacity 0, flip `data-open` on the next frame so the CSS fade runs. */
export function useFadeIn(open: boolean): boolean {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    if (!open) {
      setShown(false);
      return;
    }
    const id = requestAnimationFrame(() => setShown(true));
    return () => cancelAnimationFrame(id);
  }, [open]);
  return shown;
}

/**
 * Portal + fixed positioning + motion wrapper used by the preview, the context
 * menu and the IER tooltip. Motion itself lives in CSS (framework.css) keyed
 * on `data-open` so the global reduced-motion rules apply.
 */
export function Popover({
  open,
  x,
  y,
  width,
  height,
  zIndex,
  side,
  pointerEvents = "auto",
  children,
  style,
  ...rest
}: PopoverProps) {
  // Callers render null while closed, so an open popover is always client-side.
  const canPortal = typeof document !== "undefined";
  const shown = useFadeIn(open && canPortal);
  if (!canPortal || !open) return null;
  return createPortal(
    <div
      data-open={shown ? "true" : "false"}
      data-side={side}
      style={{ position: "fixed", left: x, top: y, width, height, zIndex, pointerEvents, ...style }}
      {...rest}
    >
      {children}
    </div>,
    document.body,
  );
}
