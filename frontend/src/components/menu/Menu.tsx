"use client";

import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import type { MenuItemModel, MenuModel } from "@/components/card/cardActions";
import { useMenuKeyboard } from "@/hooks/useMenuKeyboard";
import { MenuGroup } from "./MenuGroup";

export type MenuCloseReason = "escape" | "tab" | "select" | "outside";

export interface MenuProps extends Omit<React.HTMLAttributes<HTMLDivElement>, "onSelect" | "autoFocus"> {
  model: MenuModel;
  /** Header: card name (13 px) + subtitle (11 px). */
  title?: string;
  subtitle?: string;
  header?: React.ReactNode;
  onClose: (reason: MenuCloseReason) => void;
  /** Fires after an item's own onSelect. */
  onSelect?: (item: MenuItemModel) => void;
  /** "first" (keyboard open), "container" (pointer open), "none" (submenus). */
  autoFocus?: "first" | "container" | "none";
  isSubmenu?: boolean;
  onCloseSubmenu?: () => void;
}

/**
 * Headless-but-styled menu: role=menu, roving focus, ↑/↓/Home/End, type-ahead,
 * → / ← for submenus, Enter/Space, Esc, Tab (§4.7.3). Rendering comes from a
 * MenuModel so the action list is data (cardActions.ts), not JSX.
 */
export const Menu = forwardRef<HTMLDivElement, MenuProps>(function Menu(
  { model, title, subtitle, header, onClose, onSelect, autoFocus = "first", isSubmenu, onCloseSubmenu, className, ...rest },
  ref,
) {
  const menuRef = useRef<HTMLDivElement>(null);
  useImperativeHandle(ref, () => menuRef.current as HTMLDivElement);
  const [openSubmenuId, setOpenSubmenuId] = useState<string | null>(null);

  const kb = useMenuKeyboard(menuRef, {
    onClose: (reason) => onClose(reason),
    onCloseSubmenu: isSubmenu ? onCloseSubmenu : undefined,
    onOpenSubmenu: (el) => {
      const id = el.getAttribute("data-item-id");
      if (id) setOpenSubmenuId(id);
    },
  });

  useEffect(() => {
    if (autoFocus === "first") kb.focusFirst();
    else if (autoFocus === "container") menuRef.current?.focus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const activate = useCallback(
    (item: MenuItemModel) => {
      item.onSelect?.();
      onSelect?.(item);
      if (!item.submenu) onClose("select");
    },
    [onSelect, onClose],
  );

  return (
    <div
      ref={menuRef}
      role="menu"
      tabIndex={-1}
      aria-label={title}
      className={["dd-menu", className].filter(Boolean).join(" ")}
      onKeyDown={kb.onKeyDown}
      {...rest}
    >
      {header ??
        (title && (
          <div className="dd-menu-header">
            <p className="truncate text-[13px] font-semibold text-zinc-100">{title}</p>
            {subtitle && <p className="truncate text-[11px] text-[#9fd0ff]">{subtitle}</p>}
          </div>
        ))}
      <div className="py-1">
        {model.map((g, i) => (
          <MenuGroup
            key={g.id}
            group={g}
            first={i === 0}
            onActivate={activate}
            openSubmenuId={openSubmenuId}
            setOpenSubmenuId={setOpenSubmenuId}
            onCloseAll={onClose}
          />
        ))}
      </div>
    </div>
  );
});
