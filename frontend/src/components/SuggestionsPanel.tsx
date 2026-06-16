"use client";

import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { recommendCards } from "@/lib/api";
import { useDeck } from "@/store/deck";
import { useRelationshipStore } from "@/store/relationship";
import type { Card, DeckEntry, Reason } from "@/lib/types";

const TIER_STYLE: Record<string, { label: string; cls: string }> = {
  edhrec: { label: "EDHREC", cls: "border border-accent/50 bg-accent/10 text-accent" },
  cooccurrence: { label: "CO-OCCURRENCE", cls: "border border-cyan/50 bg-cyan/10 text-cyan" },
  color_staple: { label: "STAPLES", cls: "border border-edge bg-panel2/60 text-zinc-300" },
};

const SIGNAL_LABEL: Record<string, string> = {
  edhrec: "EDHREC",
  cooccurrence: "played with",
  synergy: "synergy",
  engine: "combo piece",
  staple: "staple",
};

export function ReasonChips({ reasons }: { reasons: Reason[] }) {
  if (reasons.length === 0) return null;
  return (
    <div className="mt-1 flex flex-wrap gap-1">
      {reasons.map((r, i) => (
        <span
          key={i}
          title={r.detail}
          className={[
            "rounded border px-1 py-0.5 text-[9px] font-medium",
            r.signal === "engine"
              ? "border-magenta/50 bg-magenta/15 text-magenta"
              : r.signal === "edhrec"
                ? "border-accent/40 bg-accent/10 text-accent"
                : "border-cyan/40 bg-cyan/10 text-cyan",
          ].join(" ")}
        >
          {SIGNAL_LABEL[r.signal] ?? r.signal} {r.value.toFixed(2)}
        </span>
      ))}
    </div>
  );
}

export function SuggestionsPanel({
  isOpen,
  onClose,
  commander,
  entries,
}: {
  isOpen: boolean;
  onClose: () => void;
  commander: Card | null;
  entries: DeckEntry[];
}) {
  const { add, cards } = useDeck();
  const openExplorer = useRelationshipStore((s) => s.open);

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [onClose]);

  const deckSig = entries
    .map((e) => e.id)
    .sort()
    .join(",");

  const { data, isFetching, error } = useQuery({
    queryKey: ["suggest", commander?.id, deckSig],
    queryFn: () =>
      recommendCards(entries, commander!.id, { limit: 24, explain: true }),
    enabled: isOpen && commander != null,
    staleTime: 30_000,
  });

  if (!isOpen) return null;

  const tier = data ? TIER_STYLE[data.tier] : null;
  // Hide anything added since the last fetch so the list reacts instantly.
  const visible = (data?.suggestions ?? []).filter((s) => !cards[s.card.id]);

  return (
    <>
      <div className="fixed inset-0 z-[120] bg-black/40" onClick={onClose} />

      <div
        className="fixed right-0 top-0 z-[125] flex h-screen w-[460px] flex-col
                   border-l border-accent/30 bg-ink/90 shadow-neon backdrop-blur-md"
        data-testid="suggestions-panel"
      >
        {/* Header */}
        <div className="flex items-start justify-between border-b border-accent/30 px-4 py-3">
          <div className="min-w-0">
            <p className="font-display text-[9px] uppercase tracking-wider text-accent">
              Suggestions
            </p>
            <p className="truncate text-sm font-semibold text-accent">
              {commander ? `for ${commander.name}` : "no commander"}
            </p>
            {tier && (
              <span
                data-testid="suggestion-tier"
                className={`mt-1 inline-block rounded px-1.5 py-0.5 text-[9px] font-bold tracking-wider ${tier.cls}`}
              >
                {tier.label}
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="ml-2 mt-0.5 rounded p-1 text-zinc-500 transition hover:bg-accent/10 hover:text-accent"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto scrollbar-thin">
          {!commander && (
            <p className="px-4 py-10 text-center text-xs text-zinc-500">
              Add a commander to the Commanders zone to get suggestions.
            </p>
          )}

          {commander && isFetching && !data && (
            <div className="flex items-center justify-center py-12">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-accent border-t-transparent" />
            </div>
          )}

          {commander && error != null && (
            <p className="px-4 py-10 text-center text-xs text-red-400">
              Failed to fetch suggestions.
            </p>
          )}

          {commander && data && visible.length === 0 && !isFetching && (
            <p className="px-4 py-10 text-center text-xs text-zinc-500">
              No suggestions — try adding a few cards first.
            </p>
          )}

          <ul className="divide-y divide-accent/10">
            {visible.map((s) => {
              const art = s.card.image_uris?.normal;
              return (
                <li
                  key={s.card.id}
                  data-testid="suggestion-row"
                  className="flex items-center gap-3 px-3 py-2 transition hover:bg-accent/[0.06] hover:shadow-neon"
                >
                  <button
                    title="Explore relationships"
                    onClick={() => openExplorer(s.card, "synergy")}
                    className="h-14 w-10 shrink-0 overflow-hidden rounded border border-accent/30 bg-zinc-900"
                  >
                    {art ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={art}
                        alt={s.card.name}
                        loading="lazy"
                        className="h-full w-full object-cover"
                      />
                    ) : (
                      <span className="block px-0.5 pt-1 text-[7px] leading-tight text-zinc-400">
                        {s.card.name}
                      </span>
                    )}
                  </button>

                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline justify-between gap-2">
                      <p className="truncate text-xs font-semibold text-zinc-200">
                        {s.card.name}
                      </p>
                      <span className="shrink-0 text-[10px] font-bold text-accent">
                        {s.score.toFixed(2)}
                      </span>
                    </div>
                    <div className="mt-0.5 h-1 w-full overflow-hidden rounded bg-panel2/60">
                      <div
                        className="h-full rounded bg-gradient-to-r from-cyan to-magenta"
                        style={{ width: `${Math.min(s.score * 100, 100)}%` }}
                      />
                    </div>
                    <ReasonChips reasons={s.reasons} />
                  </div>

                  <button
                    title="Add to deck"
                    data-testid="suggestion-add"
                    onClick={() => add(s.card)}
                    className="shrink-0 rounded-full border border-cyan/60 px-2.5 py-1.5 text-sm
                               font-bold text-cyan transition hover:bg-cyan/15 hover:shadow-neon"
                  >
                    ＋
                  </button>
                </li>
              );
            })}
          </ul>
        </div>

        {/* Footer */}
        {data && (
          <div className="border-t border-accent/30 px-4 py-2 text-[10px] text-zinc-500">
            {visible.length} suggestions · blended from EDHREC, deck co-occurrence,
            structural synergy & combo completion
          </div>
        )}
      </div>
    </>
  );
}
