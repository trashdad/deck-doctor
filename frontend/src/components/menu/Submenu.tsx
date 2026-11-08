"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { MenuItemModel } from "@/components/card/cardActions";
import { SIZE, Z } from "@/ui/tokens";
import { MenuItem } from "./MenuItem";
import { Menu } from "./Menu";

export interface SubmenuProps {
  item: MenuItemModel;
  open: boolean;
  onOpen: () => void;
  onClose: () => void;
  onActivate: (item: MenuItemModel) => void;
  onCloseAll: (reason: "escape" | "tab" | "select" | "outside") => void;
}

/**
 * A menu item that opens a nested menu beside it. The nested menu is portaled
 * to <body> (the parent menu scrolls, and an overflow container would clip it)
 * and placed to the right of the trigger, flipped left when it would overflow.
 */
export function Submenu({ item, open, onOpen, onClose, onActivate, onCloseAll }: SubmenuProps) {
  const triggerRef = useRef<HTMLDivElement>(null);
  const subRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ x: number; y: number; maxH: number } | null>(null);

  useLayoutEffect(() => {
    if (!open || !triggerRef.current || !subRef.current) {
      setPos(null);
      return;
    }
    const t = triggerRef.current.getBoundingClientRect();
    const w = SIZE.menuW;
    const h = subRef.current.offsetHeight;
    const inset = SIZE.viewportInset;
    let x = t.right - 4;
    if (x + w > window.innerWidth - inset) x = t.left + 4 - w; // flip left
    x = Math.max(inset, x);
    let y = t.top - 5;
    if (y + h > window.innerHeight - inset) y = Math.max(inset, window.innerHeight - inset - h);
    setPos({ x, y, maxH: window.innerHeight - y - inset });
  }, [open]);

  // Focus the first submenu item when opened by keyboard (→ / Enter on the trigger).
  useEffect(() => {
    if (!open || !pos) return;
    const t = triggerRef.current?.querySelector<HTMLElement>('[role="menuitem"]');
    if (t && document.activeElement === t) {
      subRef.current?.querySelector<HTMLElement>('[role^="menuitem"]')?.focus();
    }
  }, [open, pos]);

  return (
    <>
      <div ref={triggerRef}>
        <MenuItem item={item} onActivate={() => onOpen()} hasPopup expanded={open} onPointerEnter={() => onOpen()} />
      </div>
      {open &&
        typeof document !== "undefined" &&
        createPortal(
          <div
            ref={subRef}
            className="dd-submenu"
            style={{
              position: "fixed",
              left: pos?.x ?? -9999,
              top: pos?.y ?? -9999,
              zIndex: Z.menu + 1,
              visibility: pos ? "visible" : "hidden",
            }}
          >
            <Menu
              model={[{ id: `${item.id}:sub`, items: item.submenu ?? [] }]}
              aria-label={item.label}
              autoFocus="none"
              isSubmenu
              onCloseSubmenu={() => {
                onClose();
                triggerRef.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
              }}
              onClose={onCloseAll}
              onSelect={(i) => onActivate(i)}
              style={{ maxHeight: pos?.maxH }}
            />
          </div>,
          document.body,
        )}
    </>
  );
}
