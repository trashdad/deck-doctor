"use client";

import { useCallback, useEffect, useRef } from "react";

export type RovingOrientation = "grid" | "row" | "column";

export interface RovingFocusOptions {
  orientation?: RovingOrientation;
  /** Selector for the focusable items inside the container. */
  itemSelector?: string;
}

export interface RovingFocusProps {
  onKeyDown: (e: React.KeyboardEvent<HTMLElement>) => void;
  onFocusCapture: (e: React.FocusEvent<HTMLElement>) => void;
}

const DEFAULT_SELECTOR = "[data-roving-item]";

/**
 * Roving tabindex for a card surface (§4.7.4): one Tab stop per surface;
 * ←→ (and ↑↓ on grids / columns) move between items; Home/End jump.
 *
 * Items are discovered from the DOM (`itemSelector`) so the hook works for any
 * child composition. Items should render `tabIndex={-1}`; the hook promotes the
 * active one to 0 and keeps that in sync as children mount/unmount.
 */
export function useRovingFocus(
  containerRef: React.RefObject<HTMLElement>,
  { orientation = "grid", itemSelector = DEFAULT_SELECTOR }: RovingFocusOptions = {},
): RovingFocusProps {
  const active = useRef(0);

  const items = useCallback((): HTMLElement[] => {
    const c = containerRef.current;
    if (!c) return [];
    return Array.from(c.querySelectorAll<HTMLElement>(itemSelector)).filter(
      (el) => el.closest("[data-surface]") === c || !c.hasAttribute("data-surface"),
    );
  }, [containerRef, itemSelector]);

  const apply = useCallback(() => {
    const list = items();
    if (list.length === 0) return;
    if (active.current >= list.length) active.current = list.length - 1;
    list.forEach((el, i) => {
      el.tabIndex = i === active.current ? 0 : -1;
    });
  }, [items]);

  useEffect(() => {
    apply();
    const c = containerRef.current;
    if (!c || typeof MutationObserver === "undefined") return;
    const mo = new MutationObserver(() => apply());
    mo.observe(c, { childList: true, subtree: true });
    return () => mo.disconnect();
  }, [apply, containerRef]);

  const focusIndex = useCallback(
    (i: number) => {
      const list = items();
      if (list.length === 0) return;
      active.current = Math.max(0, Math.min(list.length - 1, i));
      apply();
      list[active.current].focus();
    },
    [items, apply],
  );

  const onFocusCapture = useCallback(
    (e: React.FocusEvent<HTMLElement>) => {
      const target = (e.target as HTMLElement).closest(itemSelector) as HTMLElement | null;
      if (!target) return;
      const idx = items().indexOf(target);
      if (idx >= 0 && idx !== active.current) {
        active.current = idx;
        apply();
      }
    },
    [items, apply, itemSelector],
  );

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLElement>) => {
      const list = items();
      if (list.length === 0) return;
      const target = (e.target as HTMLElement).closest(itemSelector) as HTMLElement | null;
      if (!target) return;
      const idx = list.indexOf(target);
      if (idx < 0) return;

      let cols = 1;
      if (orientation === "grid") {
        const top0 = list[0].offsetTop;
        cols = list.filter((el) => el.offsetTop === top0).length || 1;
      }
      const horizontal = orientation !== "column";
      const vertical = orientation !== "row";
      let next: number | null = null;
      switch (e.key) {
        case "ArrowRight":
          if (horizontal) next = idx + 1;
          break;
        case "ArrowLeft":
          if (horizontal) next = idx - 1;
          break;
        case "ArrowDown":
          if (vertical) next = idx + (orientation === "grid" ? cols : 1);
          break;
        case "ArrowUp":
          if (vertical) next = idx - (orientation === "grid" ? cols : 1);
          break;
        case "Home":
          next = 0;
          break;
        case "End":
          next = list.length - 1;
          break;
      }
      if (next === null) return;
      if (next < 0 || next >= list.length) {
        e.preventDefault();
        return;
      }
      e.preventDefault();
      focusIndex(next);
    },
    [items, itemSelector, orientation, focusIndex],
  );

  return { onKeyDown, onFocusCapture };
}
