"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useUI } from "@/store/ui";
import { usePreview } from "@/store/preview";
import { SIZE, Z } from "@/ui/tokens";
import {
  computeKeyboardMenuPlacement,
  computePointerPlacement,
  getViewport,
} from "@/hooks/usePopoverPlacement";
import { Popover } from "@/components/popover/Popover";
import { Menu, type MenuCloseReason } from "@/components/menu/Menu";

/**
 * The one card context menu (§4.7.3). Opened via useUI.openMenu(request).
 * Closes on Esc, outside pointer-down, item select, surface scroll > 8 px,
 * window blur and Back (popstate). Focus returns to the invoking card.
 */
export function CardContextMenu() {
  const req = useUI((s) => s.menu);
  const closeMenu = useUI((s) => s.closeMenu);
  const menuRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);

  // Suppress the preview while open.
  useEffect(() => {
    if (!req) return;
    return usePreview.getState().suppress();
  }, [req]);

  const close = useCallback(
    (reason: MenuCloseReason | "scroll" | "blur" | "back") => {
      const target = useUI.getState().menu?.returnFocusTo ?? null;
      closeMenu();
      if (target && reason !== "blur") target.focus({ preventScroll: true });
    },
    [closeMenu],
  );

  // Measure after mount, then place (flip/shift inside the viewport inset).
  useLayoutEffect(() => {
    if (!req || !menuRef.current) {
      setPos(null);
      return;
    }
    const el = menuRef.current;
    const size = { width: SIZE.menuW, height: el.offsetHeight };
    const vp = getViewport();
    if ("x" in req.at) {
      setPos(computePointerPlacement(req.at, size, vp));
    } else {
      const p = computeKeyboardMenuPlacement(req.at.anchorRect, req.at.surfaceRect, size, vp);
      setPos({ x: p.x, y: p.y });
    }
  }, [req]);

  // Focus only once the menu is positioned (a visibility:hidden element cannot take focus).
  useEffect(() => {
    if (!req || !pos || !menuRef.current) return;
    const m = menuRef.current;
    if (req.via === "keyboard") {
      const first = m.querySelector<HTMLElement>('[role^="menuitem"]');
      (first ?? m).focus({ preventScroll: true });
    } else {
      m.focus({ preventScroll: true });
    }
  }, [req, pos]);

  // Outside click, scroll > 8 px, window blur, Back, and Esc when focus is outside the menu.
  useEffect(() => {
    if (!req) return;
    // Submenus are portaled to <body>, so "inside" = the menu or any .dd-submenu.
    const inside = (n: Node | null) => {
      if (!n) return false;
      const el = n instanceof Element ? n : n.parentElement;
      return Boolean(el && (menuRef.current?.contains(el) || el.closest(".dd-submenu")));
    };
    const onDown = (e: PointerEvent) => {
      if (!inside(e.target as Node)) close("outside");
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (inside(document.activeElement)) return; // Menu handles it
      e.preventDefault();
      close("escape");
    };
    const scrollOrigin = new Map<EventTarget, number>();
    const keyOf = (t: EventTarget | null): EventTarget => (t === document || t === null ? window : t);
    const readScroll = (t: EventTarget): number =>
      t === window ? window.scrollY : (t as HTMLElement).scrollTop;
    // Snapshot the invoker's scrollable ancestors so the first scroll event already counts.
    let node: HTMLElement | null = req.returnFocusTo?.parentElement ?? null;
    while (node) {
      if (node.scrollHeight > node.clientHeight) scrollOrigin.set(node, node.scrollTop);
      node = node.parentElement;
    }
    scrollOrigin.set(window, window.scrollY);
    const onScroll = (e: Event) => {
      if (menuRef.current && e.target instanceof Node && menuRef.current.contains(e.target)) return;
      const k = keyOf(e.target);
      const now = readScroll(k);
      if (!scrollOrigin.has(k)) {
        scrollOrigin.set(k, now);
        return;
      }
      if (Math.abs(now - (scrollOrigin.get(k) ?? now)) > 8) close("scroll");
    };
    const onBlur = () => close("blur");
    const onPop = () => close("back");
    document.addEventListener("pointerdown", onDown, true);
    document.addEventListener("keydown", onKey, true);
    document.addEventListener("scroll", onScroll, { capture: true, passive: true });
    window.addEventListener("blur", onBlur);
    window.addEventListener("popstate", onPop);
    return () => {
      document.removeEventListener("pointerdown", onDown, true);
      document.removeEventListener("keydown", onKey, true);
      document.removeEventListener("scroll", onScroll, { capture: true });
      window.removeEventListener("blur", onBlur);
      window.removeEventListener("popstate", onPop);
    };
  }, [req, close]);

  if (!req) return null;

  return (
    <Popover
      open
      x={pos?.x ?? -9999}
      y={pos?.y ?? -9999}
      zIndex={Z.menu}
      className="dd-menu-floating"
      data-testid="card-menu"
      style={pos ? undefined : { visibility: "hidden" }}
    >
      <Menu
        ref={menuRef}
        model={req.model}
        title={req.title}
        subtitle={req.subtitle}
        autoFocus="none"
        onClose={(reason) => close(reason)}
      />
    </Popover>
  );
}
