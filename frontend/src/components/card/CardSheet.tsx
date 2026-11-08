"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import type { Card } from "@/lib/types";
import type { MenuItemModel, MenuModel } from "./cardActions";
import { useUI } from "@/store/ui";
import { usePreview } from "@/store/preview";
import { CardFrame } from "./CardFrame";

export interface CardSheetBodyProps {
  card: Card;
  model: MenuModel;
  onClose: () => void;
  /** Gallery: render in flow (no portal, no fixed positioning). */
  inline?: boolean;
}

function SheetRow({ item, onDone }: { item: MenuItemModel; onDone: () => void }) {
  const [open, setOpen] = useState(false);
  if (item.links) {
    return (
      <div className="flex gap-2 px-4 py-1">
        {item.links.map((l) => (
          <a
            key={l.label}
            href={l.href}
            target="_blank"
            rel="noopener noreferrer"
            className="flex min-h-[44px] flex-1 items-center justify-center rounded text-[15px] font-medium text-zinc-300 underline decoration-zinc-500/50 underline-offset-4 active:bg-accent/10 active:text-white"
          >
            {l.label} ↗
          </a>
        ))}
      </div>
    );
  }
  if (item.submenu) {
    return (
      <div>
        <button type="button" className="dd-sheet-row" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
          <span className="dd-sheet-icon" aria-hidden="true">{item.icon}</span>
          <span className="flex-1">{item.label}</span>
          <span className="text-[13px] text-zinc-400">{open ? "▴" : "▾"}</span>
        </button>
        {open && (
          <div className="border-l-2 border-accent/30 bg-ink/40 pl-4" role="group" aria-label={item.label}>
            {item.submenu.map((sub) => (
              <button
                key={sub.id}
                type="button"
                role="menuitemradio"
                aria-checked={sub.checked ?? false}
                className="dd-sheet-row"
                onClick={() => {
                  sub.onSelect?.();
                  onDone();
                }}
              >
                <span className="dd-sheet-icon" aria-hidden="true">
                  {sub.checked ? "✓" : ""}
                </span>
                <span className="flex-1">{sub.label}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }
  if (item.href) {
    return (
      <a
        href={item.href}
        target={item.external ? "_blank" : undefined}
        rel={item.external ? "noopener noreferrer" : undefined}
        className="dd-sheet-row"
        data-tone={item.tone ?? "default"}
        onClick={onDone}
      >
        <span className="dd-sheet-icon" aria-hidden="true">{item.icon}</span>
        <span className="flex-1">{item.label}</span>
        <span className="text-[13px] text-zinc-400">↗</span>
      </a>
    );
  }
  return (
    <button
      type="button"
      className="dd-sheet-row"
      data-tone={item.tone ?? "default"}
      onClick={() => {
        item.onSelect?.();
        onDone();
      }}
    >
      <span className="dd-sheet-icon" aria-hidden="true">{item.icon}</span>
      <span className="flex-1">{item.label}</span>
    </button>
  );
}

/** Large image + name/type + the context-menu actions as 44 px rows (§4.9). */
export function CardSheetBody({ card, model, onClose, inline }: CardSheetBodyProps) {
  return (
    <div
      role="dialog"
      aria-modal={inline ? undefined : true}
      aria-label={card.name}
      data-testid={inline ? "card-sheet-inline" : "card-sheet"}
      className={inline ? "dd-sheet relative max-h-none rounded-t-[14px]" : "dd-sheet"}
      style={inline ? { position: "relative", bottom: "auto" } : undefined}
    >
      <div className="flex justify-center pb-1 pt-2" aria-hidden="true">
        <span className="h-1 w-10 rounded-full bg-zinc-500/70" />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain pb-[max(8px,env(safe-area-inset-bottom))]">
        {/* 96 px art + name/type beside it; oracle text below at full width (§4.9). */}
        <div className="px-4 pb-3 pt-1">
          <div className="flex items-center gap-3">
            <CardFrame card={card} size="hero" loading="eager" className="shrink-0" style={{ width: 96 }} />
            <div className="min-w-0 flex-1">
              <p className="text-[15px] font-semibold leading-tight text-zinc-100">{card.name}</p>
              <p className="mt-0.5 text-[13px] text-zinc-400">{card.type_line}</p>
            </div>
          </div>
          {card.oracle_text && (
            <p className="mt-3 line-clamp-6 whitespace-pre-line text-[13px] leading-[18px] text-zinc-300">{card.oracle_text}</p>
          )}
        </div>
        <div role="menu" aria-label={`${card.name} actions`}>
          {model.map((g, gi) => (
            <div key={g.id} role="group">
              {gi > 0 && <div role="separator" className="dd-menu-sep" />}
              {g.items.map((item) => (
                <SheetRow key={item.id} item={item} onDone={onClose} />
              ))}
            </div>
          ))}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="mx-4 mb-2 mt-2 flex min-h-[44px] w-[calc(100%-32px)] items-center justify-center rounded border border-edge text-[15px] font-semibold text-zinc-300"
        >
          Close
        </button>
      </div>
    </div>
  );
}

/** Singleton touch sheet; opened via useUI.openSheet. Mount once per page. */
export function CardSheet() {
  const req = useUI((s) => s.sheet);
  const closeSheet = useUI((s) => s.closeSheet);
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!req) return;
    const release = usePreview.getState().suppress();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeSheet();
    };
    const onPop = () => closeSheet();
    window.addEventListener("keydown", onKey);
    window.addEventListener("popstate", onPop);
    return () => {
      release();
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("popstate", onPop);
    };
  }, [req, closeSheet]);

  if (!mounted || !req) return null;
  return createPortal(
    <>
      <div className="dd-sheet-backdrop" onPointerDown={closeSheet} aria-hidden="true" />
      <CardSheetBody card={req.card} model={req.model} onClose={closeSheet} />
    </>,
    document.body,
  );
}
