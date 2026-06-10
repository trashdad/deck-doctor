"use client";

import type { Card } from "@/lib/types";

export function CardTile({
  card,
  onClick,
  compact = false,
  badge,
  onAdd,
  onFocus,
  onInspect,
}: {
  card: Card;
  onClick?: () => void;
  compact?: boolean;
  /** Small metric pill rendered top-right (replaces the bare IER pill). */
  badge?: string;
  /** When any of these are set, a hover action bar renders over the art. */
  onAdd?: () => void;
  onFocus?: () => void;
  onInspect?: () => void;
}) {
  const art = card.image_uris?.normal;
  const hasActions = Boolean(onAdd || onFocus || onInspect);
  const pill = badge ?? (card.ier != null ? String(card.ier) : null);

  return (
    <div
      className="mtg-card group cursor-pointer select-none"
      title={`${card.name}${card.ier != null ? ` · IER ${card.ier}` : ""}`}
      onClick={onClick}
    >
      {art ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={art}
          alt={card.name}
          loading="lazy"
          onError={(e) => {
            (e.currentTarget as HTMLImageElement).style.display = "none";
            const fb = e.currentTarget.nextElementSibling as HTMLElement | null;
            if (fb) fb.style.display = "flex";
          }}
        />
      ) : null}
      <div className="mtg-fallback" style={{ display: art ? "none" : "flex" }}>
        <div className="flex items-start justify-between gap-1">
          <span className="font-semibold text-zinc-100">{card.name}</span>
          <span className="text-zinc-400">{card.cmc > 0 ? card.cmc : ""}</span>
        </div>
        <div className="text-zinc-400">{card.type_line}</div>
        {!compact && (
          <div className="line-clamp-5 text-zinc-500">{card.oracle_text}</div>
        )}
        <div className="flex items-center justify-between text-zinc-400">
          <span>{card.color_identity.join("") || "C"}</span>
          {card.ier != null && (
            <span className="rounded bg-accent/20 px-1 text-accent">
              IER {card.ier}
            </span>
          )}
        </div>
      </div>

      {pill && (
        <span className="absolute right-1 top-1 z-10 rounded bg-black/75 px-1 text-[10px] font-semibold text-accent">
          {pill}
        </span>
      )}

      {hasActions && (
        <div
          className="absolute inset-x-0 bottom-0 z-10 flex items-stretch justify-center gap-px
                     bg-black/80 opacity-0 transition-opacity group-hover:opacity-100"
        >
          {onAdd && (
            <button
              title="Add to deck"
              onClick={(e) => {
                e.stopPropagation();
                onAdd();
              }}
              className="flex-1 py-1.5 text-[11px] font-bold text-accent hover:bg-accent/20"
            >
              ＋
            </button>
          )}
          {onFocus && (
            <button
              title="Focus explorer on this card"
              onClick={(e) => {
                e.stopPropagation();
                onFocus();
              }}
              className="flex-1 py-1.5 text-[11px] font-bold text-sky-300 hover:bg-sky-400/20"
            >
              ◎
            </button>
          )}
          {onInspect && (
            <button
              title="Inspect this pair"
              onClick={(e) => {
                e.stopPropagation();
                onInspect();
              }}
              className="flex-1 py-1.5 text-[11px] font-bold text-zinc-300 hover:bg-white/15"
            >
              ⓘ
            </button>
          )}
        </div>
      )}
    </div>
  );
}
