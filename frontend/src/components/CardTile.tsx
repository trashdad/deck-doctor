"use client";

import { useCallback, useId, useRef, useState } from "react";
import type { Card } from "@/lib/types";
import { CardInteractive } from "./card/CardInteractive";
import { IerTooltip } from "./IerTooltip";
import { usePreview } from "@/store/preview";

/**
 * Legacy-prop card tile for the panels (commanders tab, SemanticFinder,
 * TemplatePanel, WinconHelperPanel, OraclePhrasePanel, RelationshipExplorer,
 * DeckCombosPanel, EngineStaplesPanel). Now a thin wrapper over
 * `CardInteractive size="tile" context="find"`:
 *
 *   - hover / focus → the singleton `CardPreview` (via useHoverIntent)
 *   - right-click / Shift+F10 / Space → the singleton `CardContextMenu`
 *   - long-press (touch) → `CardSheet`
 *   - left-click keeps the legacy semantics: calls `onClick` and *bubbles* to
 *     the parent (several consumers put the click handler on a wrapper div),
 *     instead of opening the menu.
 *
 * Surface: CardInteractive expects a `[data-surface]` ancestor whose id it
 * echoes as `surfaceId`. These consumer grids have none, so by default the
 * tile hosts `data-surface` on itself — a one-card surface. The preview and
 * keyboard-menu placement then anchor beside the tile (exactly the DOM
 * fallback CardInteractive/useHoverIntent already apply via
 * `closest("[data-surface]") ?? el`), and the contract "surfaceId matches the
 * nearest [data-surface]" stays literally true. Consumers that later wrap
 * tiles in a `CardSurface` pass its id as `surfaceId` and the self-surface is
 * dropped. Nothing in components/card/** had to change.
 */
export function CardTile({
  card,
  onClick,
  badge,
  onAdd,
  onFocus,
  onInspect,
  surfaceId,
}: {
  card: Card;
  onClick?: () => void;
  /** Accepted for compatibility; CardFrame decides what the fallback frame shows. */
  compact?: boolean;
  /** Small metric pill rendered top-right (replaces the bare IER pill). */
  badge?: string;
  /** When any of these are set, a hover action bar renders over the art. */
  onAdd?: () => void;
  onFocus?: () => void;
  onInspect?: () => void;
  /** Id of an enclosing `CardSurface`. Omit → the tile is its own surface. */
  surfaceId?: string;
}) {
  const ownId = useId();
  const hasActions = Boolean(onAdd || onFocus || onInspect);
  const pill = badge ?? (card.ier != null ? String(card.ier) : null);

  // IER tooltip: hovering the pill shows the breakdown and suppresses the big
  // preview (refcounted via usePreview.suppress so a pending hover-open cannot
  // fire underneath the tooltip). Released on leave / unmount.
  const [ierActive, setIerActive] = useState(false);
  const releaseRef = useRef<(() => void) | null>(null);
  const enterPill = useCallback(() => {
    if (!releaseRef.current) releaseRef.current = usePreview.getState().suppress();
    setIerActive(true);
  }, []);
  const leavePill = useCallback(() => {
    releaseRef.current?.();
    releaseRef.current = null;
    setIerActive(false);
  }, []);
  const pillRef = useCallback(
    (el: HTMLSpanElement | null) => {
      if (el === null) leavePill();
    },
    [leavePill],
  );

  const handleClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      onClick?.();
      // Legacy left-click: no menu, let it bubble to wrapper handlers.
      e.preventDefault();
    },
    [onClick],
  );

  return (
    <>
      <CardInteractive
        card={card}
        size="tile"
        context="find"
        surfaceId={surfaceId ?? ownId}
        data-surface={surfaceId ? undefined : ownId}
        primary={onClick}
        // Grid consumers size the tile by the cell, not the 160 px default.
        className="!w-full"
        // Native tooltip with name + type line (cheap, useful on dense grids).
        title={card.type_line ? `${card.name} — ${card.type_line}` : card.name}
        // The custom pill below carries the hover handlers CardFrame's badge lacks.
        state={{ ierPill: null }}
        onClick={handleClick}
      >
        {pill && (
          <span
            ref={pillRef}
            className="dd-badge dd-badge-tr dd-badge-ier cursor-default"
            style={{ pointerEvents: "auto" }}
            onMouseEnter={enterPill}
            onMouseLeave={leavePill}
            title={`IER: ${pill}`}
          >
            {pill}
          </span>
        )}

        {hasActions && (
          <div className="dd-actions">
            {onAdd && (
              <button
                type="button"
                title="Add to deck"
                onClick={(e) => {
                  e.stopPropagation();
                  onAdd();
                }}
                className="text-accent hover:bg-accent/20"
              >
                ＋
              </button>
            )}
            {onFocus && (
              <button
                type="button"
                title="Focus explorer on this card"
                onClick={(e) => {
                  e.stopPropagation();
                  onFocus();
                }}
                className="text-cyan hover:bg-cyan/20"
              >
                ◎
              </button>
            )}
            {onInspect && (
              <button
                type="button"
                title="Inspect this pair"
                onClick={(e) => {
                  e.stopPropagation();
                  onInspect();
                }}
                className="text-[#c8b6ff] hover:bg-magenta/20"
              >
                ⓘ
              </button>
            )}
          </div>
        )}
      </CardInteractive>

      {card.ier != null && <IerTooltip cardId={card.id} ier={card.ier} active={ierActive} />}
    </>
  );
}
