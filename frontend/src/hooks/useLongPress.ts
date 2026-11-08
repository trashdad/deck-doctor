"use client";

import { useCallback, useEffect, useRef } from "react";
import { TIMING } from "@/ui/tokens";

export interface LongPressOptions {
  onLongPress: (e: PointerEvent | React.PointerEvent<HTMLElement>) => void;
  /** Fires on a short tap (pointer up before the delay, no move). */
  onTap?: (e: React.PointerEvent<HTMLElement>) => void;
  delay?: number;
  /** Movement beyond this cancels (px). */
  moveTolerance?: number;
  enabled?: boolean;
  /** Restrict to these pointer types (default: touch only). */
  pointerTypes?: ReadonlyArray<string>;
}

export interface LongPressHandlers {
  onPointerDown: (e: React.PointerEvent<HTMLElement>) => void;
  onPointerMove: (e: React.PointerEvent<HTMLElement>) => void;
  onPointerUp: (e: React.PointerEvent<HTMLElement>) => void;
  onPointerCancel: (e: React.PointerEvent<HTMLElement>) => void;
  /** True right after a long press fired — callers use it to swallow the click. */
  consumedRef: React.MutableRefObject<boolean>;
}

/** 450 ms long-press; cancels on move > 8 px, scroll, pointer cancel. */
export function useLongPress({
  onLongPress,
  onTap,
  delay = TIMING.longPress,
  moveTolerance = 8,
  enabled = true,
  pointerTypes = ["touch"],
}: LongPressOptions): LongPressHandlers {
  const timer = useRef<number | null>(null);
  const start = useRef<{ x: number; y: number } | null>(null);
  const consumedRef = useRef(false);
  const cbRef = useRef({ onLongPress, onTap });
  cbRef.current = { onLongPress, onTap };

  const cancel = useCallback(() => {
    if (timer.current !== null) {
      window.clearTimeout(timer.current);
      timer.current = null;
    }
    start.current = null;
  }, []);

  useEffect(() => {
    const onScroll = () => cancel();
    window.addEventListener("scroll", onScroll, { capture: true, passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll, { capture: true });
      cancel();
    };
  }, [cancel]);

  const onPointerDown = useCallback(
    (e: React.PointerEvent<HTMLElement>) => {
      if (!enabled || !pointerTypes.includes(e.pointerType)) return;
      consumedRef.current = false;
      start.current = { x: e.clientX, y: e.clientY };
      const ev = e;
      timer.current = window.setTimeout(() => {
        timer.current = null;
        start.current = null;
        consumedRef.current = true;
        cbRef.current.onLongPress(ev);
      }, delay);
    },
    [enabled, delay, pointerTypes],
  );

  const onPointerMove = useCallback(
    (e: React.PointerEvent<HTMLElement>) => {
      if (!start.current) return;
      const dx = e.clientX - start.current.x;
      const dy = e.clientY - start.current.y;
      if (Math.hypot(dx, dy) > moveTolerance) cancel();
    },
    [cancel, moveTolerance],
  );

  const onPointerUp = useCallback(
    (e: React.PointerEvent<HTMLElement>) => {
      if (!enabled || !pointerTypes.includes(e.pointerType)) return;
      const wasPending = timer.current !== null && start.current !== null;
      cancel();
      if (wasPending) {
        consumedRef.current = true; // swallow the synthetic click that follows a tap
        cbRef.current.onTap?.(e);
      }
    },
    [enabled, pointerTypes, cancel],
  );

  const onPointerCancel = useCallback(() => cancel(), [cancel]);

  return { onPointerDown, onPointerMove, onPointerUp, onPointerCancel, consumedRef };
}
