"use client";

import { useCallback, useRef } from "react";

export interface MenuKeyboardOptions {
  /** Called for → on an item with a submenu, and Enter/Space on it. */
  onOpenSubmenu?: (item: HTMLElement) => void;
  /** Called for ← (closes this submenu, if it is one). */
  onCloseSubmenu?: () => void;
  /** Esc / Tab: close the whole menu (Tab also returns focus to the invoker). */
  onClose: (reason: "escape" | "tab") => void;
  /** Type-ahead buffer lifetime (ms). */
  typeAheadMs?: number;
}

export interface MenuKeyboard {
  onKeyDown: (e: React.KeyboardEvent<HTMLElement>) => void;
  focusFirst: () => void;
  focusLast: () => void;
  items: () => HTMLElement[];
}

const ITEM_SELECTOR = '[role="menuitem"],[role="menuitemcheckbox"],[role="menuitemradio"]';

/**
 * WAI-ARIA menu keyboard semantics (§4.7.3): ↑/↓ move with wrap, Home/End,
 * type-ahead by first letters (250 ms buffer), → opens a submenu, ← closes it,
 * Enter/Space activates, Tab closes and returns focus, Esc closes.
 *
 * Items are the role=menuitem* elements whose nearest [role=menu] is this one
 * (so nested submenus own their own items).
 */
export function useMenuKeyboard(
  menuRef: React.RefObject<HTMLElement>,
  { onOpenSubmenu, onCloseSubmenu, onClose, typeAheadMs = 250 }: MenuKeyboardOptions,
): MenuKeyboard {
  const buffer = useRef("");
  const bufferT = useRef<number | null>(null);

  const items = useCallback((): HTMLElement[] => {
    const m = menuRef.current;
    if (!m) return [];
    return Array.from(m.querySelectorAll<HTMLElement>(ITEM_SELECTOR)).filter(
      (el) => el.closest('[role="menu"]') === m && el.getAttribute("aria-disabled") !== "true",
    );
  }, [menuRef]);

  const focusAt = useCallback(
    (i: number) => {
      const list = items();
      if (list.length === 0) return;
      const n = ((i % list.length) + list.length) % list.length;
      list[n].focus();
    },
    [items],
  );

  const focusFirst = useCallback(() => focusAt(0), [focusAt]);
  const focusLast = useCallback(() => focusAt(-1), [focusAt]);

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLElement>) => {
      const m = menuRef.current;
      if (!m) return;
      // Only handle keys for THIS menu level (a nested submenu handles its own).
      const t = e.target as HTMLElement;
      if (t.closest('[role="menu"]') !== m) return;

      const list = items();
      const current = t.closest(ITEM_SELECTOR) as HTMLElement | null;
      const idx = current ? list.indexOf(current) : -1;

      switch (e.key) {
        case "ArrowDown":
          e.preventDefault();
          e.stopPropagation();
          focusAt(idx + 1);
          return;
        case "ArrowUp":
          e.preventDefault();
          e.stopPropagation();
          focusAt(idx < 0 ? -1 : idx - 1);
          return;
        case "Home":
          e.preventDefault();
          e.stopPropagation();
          focusAt(0);
          return;
        case "End":
          e.preventDefault();
          e.stopPropagation();
          focusAt(-1);
          return;
        case "ArrowRight":
          if (current && current.getAttribute("aria-haspopup") === "menu") {
            e.preventDefault();
            e.stopPropagation();
            onOpenSubmenu?.(current);
          }
          return;
        case "ArrowLeft":
          if (onCloseSubmenu) {
            e.preventDefault();
            e.stopPropagation();
            onCloseSubmenu();
          }
          return;
        case "Enter":
        case " ":
          if (current) {
            e.preventDefault();
            e.stopPropagation();
            if (current.getAttribute("aria-haspopup") === "menu") onOpenSubmenu?.(current);
            else current.click();
          }
          return;
        case "Escape":
          e.preventDefault();
          e.stopPropagation();
          if (onCloseSubmenu) onCloseSubmenu();
          else onClose("escape");
          return;
        case "Tab":
          e.preventDefault();
          e.stopPropagation();
          onClose("tab");
          return;
      }

      // Type-ahead: printable single characters.
      if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        e.stopPropagation();
        if (bufferT.current !== null) window.clearTimeout(bufferT.current);
        buffer.current += e.key.toLowerCase();
        bufferT.current = window.setTimeout(() => {
          buffer.current = "";
          bufferT.current = null;
        }, typeAheadMs);
        const q = buffer.current;
        const start = idx + 1;
        for (let k = 0; k < list.length; k++) {
          const el = list[(start + k) % list.length];
          const label = (el.textContent ?? "").trim().toLowerCase();
          if (label.startsWith(q)) {
            el.focus();
            return;
          }
        }
      }
    },
    [menuRef, items, focusAt, onOpenSubmenu, onCloseSubmenu, onClose, typeAheadMs],
  );

  return { onKeyDown, focusFirst, focusLast, items };
}
