"use client";

import type { Card } from "@/lib/types";

export function CardTile({
  card,
  onClick,
  compact = false,
}: {
  card: Card;
  onClick?: () => void;
  compact?: boolean;
}) {
  const art = card.image_uris?.normal;
  return (
    <div
      className="mtg-card cursor-pointer select-none"
      title={`${card.name}${card.ier != null ? ` · IER ${card.ier}` : ""}`}
      onClick={onClick}
    >
      {/* Art loads from Scryfall in dev; the fallback frame renders the card
          text so the layout still reads on a broken/offline image link. */}
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
      {card.ier != null && art && (
        <span className="absolute right-1 top-1 rounded bg-black/70 px-1 text-[10px] text-accent">
          {card.ier}
        </span>
      )}
    </div>
  );
}
