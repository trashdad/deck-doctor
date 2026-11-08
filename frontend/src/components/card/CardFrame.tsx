"use client";

import { forwardRef, useState } from "react";
import type { Card } from "@/lib/types";

export type CardSize = "pile" | "tile" | "thumb" | "hero"; // 70 | 160 | 40×56 | preview

export type CardState = {
  ghost?: "additional" | "bridge";
  offColor?: boolean;
  cutCandidate?: boolean;
  selected?: boolean;
  dragging?: boolean;
  wincon?: boolean;
  /** Text for the top-right pill (IER today). null/undefined → none. */
  ierPill?: string | null;
  /** Gallery/debug: force the hover affordance on. */
  forceHover?: boolean;
};

export interface CardFrameProps extends React.HTMLAttributes<HTMLDivElement> {
  card: Card;
  size: CardSize;
  state?: CardState;
  className?: string;
  /** Overlays: action bar, remove handle. Rendered inside the frame. */
  children?: React.ReactNode;
  /** `eager` for the preview; default lazy. */
  loading?: "eager" | "lazy";
}

const WIDTH: Record<CardSize, string> = {
  pile: "w-[70px]",
  tile: "w-[160px]",
  thumb: "w-10",
  hero: "w-full",
};

/**
 * Pure visual card: art (or the fallback frame), corner badges, state rings.
 * No handlers of its own — CardInteractive adds behaviour on top.
 * Takes a `Card` object, never a name (plan §5.2).
 */
export const CardFrame = forwardRef<HTMLDivElement, CardFrameProps>(function CardFrame(
  { card, size, state = {}, className, children, loading = "lazy", ...rest },
  ref,
) {
  const art = card.image_uris?.normal;
  const [broken, setBroken] = useState(false);
  const showArt = Boolean(art) && !broken;
  const wincon = state.wincon ?? card.wincon ?? false;
  // Numbers and glyph badges only at tile/hero (§3.3); pile gets the 14 px win-con mark,
  // thumb a 10 px dot. Ghost / off-color text strips collapse to a 2 px bar below tile.
  const large = size === "tile" || size === "hero";
  const pill = !large || state.cutCandidate ? null : state.ierPill ?? (card.ier != null ? String(card.ier) : null);

  return (
    <div
      ref={ref}
      className={["dd-card", WIDTH[size], className].filter(Boolean).join(" ")}
      data-size={size}
      data-force-hover={state.forceHover ? "true" : undefined}
      data-ghost={state.ghost}
      data-off-color={state.offColor ? "true" : undefined}
      data-cut={state.cutCandidate ? "true" : undefined}
      data-selected={state.selected ? "true" : undefined}
      data-dragging={state.dragging ? "true" : undefined}
      {...rest}
    >
      {showArt ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={art} alt="" loading={loading} draggable={false} onError={() => setBroken(true)} />
      ) : (
        <div className="dd-fallback" aria-hidden="true">
          <div className="flex items-start justify-between gap-1">
            <span className="font-semibold text-zinc-100">{card.name}</span>
            {size !== "thumb" && size !== "pile" && card.cmc > 0 && (
              <span className="text-zinc-400">{card.cmc}</span>
            )}
          </div>
          {size !== "thumb" && <div className="text-zinc-400">{card.type_line}</div>}
          {(size === "tile" || size === "hero") && (
            <div className={size === "hero" ? "line-clamp-[12] text-zinc-300" : "line-clamp-4 text-zinc-500"}>
              {card.oracle_text}
            </div>
          )}
          {size !== "thumb" && (
            <div className="flex items-center justify-between text-zinc-400">
              <span>{card.color_identity.join("") || "C"}</span>
              {card.power != null && (
                <span>
                  {card.power}/{card.toughness}
                </span>
              )}
            </div>
          )}
        </div>
      )}

      {wincon && <span className="dd-badge dd-badge-tl dd-badge-wincon" title="Win condition" />}
      {state.cutCandidate && large ? (
        <span className="dd-badge dd-badge-tr dd-badge-cut" title="Cut candidate">
          ✂
        </span>
      ) : (
        pill && (
          <span className="dd-badge dd-badge-tr dd-badge-ier" title={`IER ${pill}`}>
            {pill}
          </span>
        )
      )}

      {state.ghost &&
        (large ? (
          <span className="dd-strip text-cyan">{state.ghost}</span>
        ) : (
          <span className="dd-bar" data-kind="ghost" title={`Ghost: ${state.ghost}`} />
        ))}
      {state.offColor &&
        (large ? (
          <span className="dd-strip text-zinc-300" title="Off-color for this commander">
            ⊘ Off-color
          </span>
        ) : (
          <span className="dd-bar" data-kind="off-color" title="Off-color for this commander" />
        ))}

      {children}
    </div>
  );
});
