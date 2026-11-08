"use client";

import type { MenuItemModel } from "@/components/card/cardActions";
import { MenuIcon } from "./icons";

export interface MenuItemProps {
  item: MenuItemModel;
  onActivate: (item: MenuItemModel) => void;
  /** Submenu trigger state (set by Submenu). */
  hasPopup?: boolean;
  expanded?: boolean;
  onPointerEnter?: (e: React.PointerEvent<HTMLElement>) => void;
}

/**
 * One menu row: button, link, or a row of links (the buy row).
 * Layout: [20 px gutter][label][hint column]. The gutter holds the row's icon
 * or — for radio/check items — the check mark, so labels never shift (review #9).
 * The hint column holds the shortcut or the submenu chevron, right-aligned.
 */
export function MenuItem({ item, onActivate, hasPopup, expanded, onPointerEnter }: MenuItemProps) {
  const disabled = item.disabled === true;
  const common = {
    className: "dd-menu-item",
    "data-tone": item.tone ?? "default",
    "data-item-id": item.id,
    "aria-disabled": disabled || undefined,
    tabIndex: -1,
    onPointerEnter,
  } as const;
  const activate = () => {
    if (!disabled) onActivate(item);
  };

  if (item.links) {
    return (
      <div role="group" aria-label={item.label} data-item-id={item.id}>
        <div className="dd-menu-item" aria-hidden="true" style={{ minHeight: 28, color: "#9fd0ff", fontSize: 11 }}>
          <span className="dd-menu-icon">{item.icon}</span>
          <span className="dd-menu-label">{item.label}</span>
        </div>
        <div className="dd-menu-links">
          {item.links.map((l) => (
            <a
              key={l.label}
              role="menuitem"
              tabIndex={-1}
              href={l.href}
              target="_blank"
              rel="noopener noreferrer"
              onClick={() => onActivate(item)}
            >
              {l.label} ↗
            </a>
          ))}
        </div>
      </div>
    );
  }

  const radio = item.checked !== undefined;
  const body = (
    <>
      <span className="dd-menu-icon" aria-hidden="true" data-checked={radio ? String(item.checked) : undefined}>
        {radio ? item.checked && <MenuIcon name="check" /> : item.icon}
      </span>
      <span className="dd-menu-label">{item.label}</span>
      {hasPopup ? (
        <span className="dd-menu-shortcut" aria-hidden="true" data-kind="submenu">
          <MenuIcon name="chevron" size={14} />
        </span>
      ) : item.shortcut ? (
        <span className="dd-menu-shortcut" aria-hidden="true">
          {item.shortcut}
        </span>
      ) : null}
    </>
  );

  if (item.href) {
    return (
      <a
        role="menuitem"
        href={disabled ? undefined : item.href}
        target={item.external ? "_blank" : undefined}
        rel={item.external ? "noopener noreferrer" : undefined}
        onClick={activate}
        {...common}
      >
        {body}
      </a>
    );
  }

  return (
    <button
      type="button"
      role={radio ? "menuitemradio" : "menuitem"}
      aria-checked={radio ? item.checked : undefined}
      aria-haspopup={hasPopup ? "menu" : undefined}
      aria-expanded={hasPopup ? expanded : undefined}
      onClick={activate}
      {...common}
    >
      {body}
    </button>
  );
}
