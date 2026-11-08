"use client";

import { useEffect } from "react";
import { usePreview } from "@/store/preview";
import { Z } from "@/ui/tokens";
import { computePlacement, getViewport, previewSize, usePopoverPlacement } from "@/hooks/usePopoverPlacement";
import { getActiveAnchor } from "@/hooks/useHoverIntent";
import { Popover } from "@/components/popover/Popover";
import { CardFrame } from "./CardFrame";

declare global {
  interface Window {
    /** Test hook: how many times the preview element has mounted (P3). */
    __ddPreviewMounts?: number;
  }
}

function MountCounter() {
  useEffect(() => {
    window.__ddPreviewMounts = (window.__ddPreviewMounts ?? 0) + 1;
  }, []);
  return null;
}

/**
 * The one hover/focus preview (§4.7.1): element-anchored, portaled, placed
 * beside the surface the pointer is in, never over it when any side fits.
 * Mount once per page (next to CardContextMenu and ToastHost).
 */
export function CardPreview() {
  const card = usePreview((s) => s.card);
  const open = usePreview((s) => s.open);
  const anchorRect = usePreview((s) => s.anchorRect);
  const surfaceRect = usePreview((s) => s.surfaceRect);
  const anchorId = usePreview((s) => s.anchorId);

  const placed = usePopoverPlacement(() => {
    if (!open || !anchorRect || !surfaceRect) return null;
    const vp = getViewport();
    const size = previewSize(vp);
    // Re-measure the live anchor on scroll/resize; fall back to the stored rects.
    const live = getActiveAnchor();
    const anchor = live ? live.el.getBoundingClientRect() : anchorRect;
    const surface = live ? live.surfaceEl.getBoundingClientRect() : surfaceRect;
    return { size, ...computePlacement({ anchor, surface, size, viewport: vp }) };
  }, [open, anchorRect, surfaceRect]);

  if (!open || !card || !placed) return null;

  return (
    <Popover
      open
      x={placed.x}
      y={placed.y}
      width={placed.size.width}
      height={placed.size.height}
      zIndex={Z.preview}
      side={placed.side}
      pointerEvents="none"
      className="dd-preview"
      data-testid="card-preview"
      data-anchor-id={anchorId ?? undefined}
      data-fits={placed.fits ? "true" : "false"}
      role="img"
      aria-label={`${card.name} card image`}
    >
      <MountCounter />
      <CardFrame card={card} size="hero" loading="eager" state={{ ierPill: null }} className="h-full !shadow-none" />
    </Popover>
  );
}
