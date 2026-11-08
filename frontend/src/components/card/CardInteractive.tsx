"use client";

import { forwardRef, useCallback, useId, useRef } from "react";
import type { Zone } from "@/lib/zones";
import { useUI, type CardContext } from "@/store/ui";
import { usePreview, toRect } from "@/store/preview";
import { useHoverIntent, hidePreviewNow } from "@/hooks/useHoverIntent";
import { useLongPress } from "@/hooks/useLongPress";
import { getPointerKind, isCoarsePointer } from "@/hooks/usePointerKind";
import { CardFrame, type CardFrameProps } from "./CardFrame";
import { buildCardActions } from "./cardActions";
import { useCardActionDeps } from "./CardActionsContext";

export type { CardContext };

export interface CardInteractiveProps extends CardFrameProps {
  context: CardContext;
  /** Must match the nearest [data-surface] ancestor's id. */
  surfaceId: string;
  /** Enter / tap-primary (Add, or open the menu on the board). */
  primary?: () => void;
  onRemove?: () => void;
  /** suggest | cut | tuneup rows: toggles the row's evidence. */
  onWhy?: () => void;
  /** deck context: current lane. */
  zone?: Zone;
  /** dnd-kit listeners/attributes (board only). */
  dragHandle?: React.HTMLAttributes<HTMLElement>;
  ariaLabel?: string;
}

/**
 * CardFrame + behaviour (§4.7): hover-intent preview, focus preview, right-click /
 * Shift+F10 / click menu, touch tap + long-press sheet, keyboard primary.
 * Renders tabIndex=-1 and data-roving-item for the surface's roving focus.
 */
export const CardInteractive = forwardRef<HTMLDivElement, CardInteractiveProps>(function CardInteractive(
  { context, surfaceId, primary, onRemove, onWhy, zone, dragHandle, ariaLabel, card, state, onKeyDown, onClick, onContextMenu, ...frame },
  ref,
) {
  const elRef = useRef<HTMLDivElement | null>(null);
  const setRef = useCallback(
    (el: HTMLDivElement | null) => {
      elRef.current = el;
      if (typeof ref === "function") ref(el);
      else if (ref) ref.current = el;
    },
    [ref],
  );
  const descId = useId();
  const pageDeps = useCardActionDeps();
  const openMenu = useUI((s) => s.openMenu);
  const openSheet = useUI((s) => s.openSheet);

  const coarse = typeof window !== "undefined" && isCoarsePointer();
  const hover = useHoverIntent({ card, enabled: !coarse });

  const buildModel = useCallback(
    () => buildCardActions(context, card, { ...pageDeps, zone, why: onWhy }),
    [context, card, pageDeps, zone, onWhy],
  );

  const openMenuAt = useCallback(
    (via: "pointer" | "keyboard", at?: { x: number; y: number }) => {
      const el = elRef.current;
      if (!el) return;
      hidePreviewNow();
      const surfaceEl = (el.closest("[data-surface]") as HTMLElement | null) ?? el;
      openMenu({
        model: buildModel(),
        title: card.name,
        subtitle: card.type_line,
        at:
          via === "pointer" && at
            ? at
            : { anchorRect: toRect(el.getBoundingClientRect()), surfaceRect: toRect(surfaceEl.getBoundingClientRect()) },
        returnFocusTo: el,
        via,
      });
    },
    [openMenu, buildModel, card],
  );

  const openSheetNow = useCallback(() => {
    hidePreviewNow();
    openSheet({ card, context, model: buildModel() });
  }, [openSheet, card, context, buildModel]);

  const press = useLongPress({
    onLongPress: openSheetNow,
    onTap: openSheetNow,
    enabled: true,
    pointerTypes: ["touch"],
  });

  const handleClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      onClick?.(e);
      if (e.defaultPrevented) return;
      if ((e.target as HTMLElement).closest("button,a")) return; // action bar / remove handle
      if (press.consumedRef.current) {
        press.consumedRef.current = false;
        return;
      }
      if (getPointerKind() === "touch") {
        openSheetNow();
        return;
      }
      if (e.detail === 0) return; // keyboard-synthesised click: Enter/Space handle it
      e.stopPropagation();
      openMenuAt("pointer", { x: e.clientX, y: e.clientY });
    },
    [onClick, press.consumedRef, openSheetNow, openMenuAt],
  );

  const handleContextMenu = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      onContextMenu?.(e);
      e.preventDefault();
      e.stopPropagation();
      if (getPointerKind() === "touch") return; // long-press already opened the sheet
      openMenuAt("pointer", { x: e.clientX, y: e.clientY });
    },
    [onContextMenu, openMenuAt],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      dragHandle?.onKeyDown?.(e);
      onKeyDown?.(e);
      if (e.defaultPrevented || e.target !== e.currentTarget) return;
      const key = e.key;
      if ((key === "F10" && e.shiftKey) || key === "ContextMenu") {
        e.preventDefault();
        openMenuAt("keyboard");
      } else if (key === "Enter") {
        e.preventDefault();
        if (primary) primary();
        else openMenuAt("keyboard");
      } else if (key === " ") {
        e.preventDefault();
        openMenuAt("keyboard");
      } else if (key === "Delete" || key === "Backspace") {
        if (onRemove) {
          e.preventDefault();
          onRemove();
        }
      } else if (key === "m" || key === "M") {
        if (context === "deck") {
          e.preventDefault();
          openMenuAt("keyboard");
        }
      } else if (key === "?") {
        if (onWhy) {
          e.preventDefault();
          onWhy();
        }
      } else if (key === "Escape") {
        if (usePreview.getState().open) {
          e.preventDefault();
          hidePreviewNow();
        } else {
          (e.currentTarget as HTMLElement).blur();
        }
      }
    },
    [dragHandle, onKeyDown, openMenuAt, primary, onRemove, context, onWhy],
  );

  const handlePointerDown = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      press.onPointerDown(e);
      dragHandle?.onPointerDown?.(e);
    },
    [press, dragHandle],
  );

  const label = ariaLabel ?? `${card.name}${card.type_line ? `, ${card.type_line}` : ""}`;

  return (
    <>
      <CardFrame
        ref={setRef}
        card={card}
        state={state}
        {...dragHandle}
        {...frame}
        className={["dd-interactive cursor-pointer", frame.className].filter(Boolean).join(" ")}
        role="button"
        tabIndex={-1}
        aria-label={label}
        aria-haspopup="menu"
        aria-describedby={descId}
        data-roving-item=""
        data-card-id={card.id}
        data-context={context}
        data-surface-id={surfaceId}
        onPointerEnter={hover.onPointerEnter}
        onPointerLeave={hover.onPointerLeave}
        onFocus={hover.onFocus}
        onBlur={hover.onBlur}
        onPointerDown={handlePointerDown}
        onPointerMove={press.onPointerMove}
        onPointerUp={press.onPointerUp}
        onPointerCancel={press.onPointerCancel}
        onClick={handleClick}
        onContextMenu={handleContextMenu}
        onKeyDown={handleKeyDown}
      >
        {frame.children}
      </CardFrame>
      {/* Screen readers get the card content without the visual popover (§4.7.1). */}
      <span id={descId} className="sr-only">
        {card.type_line}. {card.oracle_text}
      </span>
    </>
  );
});
