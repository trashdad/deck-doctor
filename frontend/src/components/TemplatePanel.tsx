"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { themeSuggest } from "@/lib/api";
import { useDeck } from "@/store/deck";
import { useTemplateStore } from "@/store/template";
import { TEMPLATE_CATEGORIES, type Card } from "@/lib/types";
import { CardTile } from "./CardTile";

const CAT_LABEL: Record<string, string> = {
  land: "Lands",
  ramp: "Ramp",
  card_draw: "Card Draw",
  removal: "Removal",
  board_wipe: "Board Wipes",
};
// category -> deck zone (to overlay the live deck count on each target bar)
const CAT_ZONE: Record<string, string> = {
  land: "Lands",
  ramp: "Ramp",
  card_draw: "Card Draw",
  removal: "Removal",
  board_wipe: "Board Wipes",
};
const ZONE_TO_CAT: Record<string, string> = Object.fromEntries(
  Object.entries(CAT_ZONE).map(([c, z]) => [z, c]),
);

/** One composition target with the live deck count overlaid + edit steppers. */
function CompositionBar({
  cat,
  target,
  current,
  onSet,
}: {
  cat: string;
  target: number;
  current: number;
  onSet: (n: number) => void;
}) {
  const met = current >= target;
  const fill = target > 0 ? Math.min(current / target, 1) * 100 : 0;
  return (
    <div className="flex items-center gap-2">
      <span className="w-20 shrink-0 text-[11px] text-zinc-400">{CAT_LABEL[cat]}</span>
      <div className="relative h-4 flex-1 overflow-hidden rounded-sm border border-edge/70 bg-ink">
        {/* target ruler ticks */}
        <div
          className={`h-full transition-all ${met ? "bg-accent/80" : "bg-accent/40"}`}
          style={{ width: `${fill}%` }}
        />
        <span className="absolute inset-0 flex items-center justify-center text-[9px] font-semibold tracking-wide text-zinc-200">
          {current} / {target}
        </span>
      </div>
      <div className="flex shrink-0 items-center gap-0.5">
        <button
          onClick={() => onSet(target - 1)}
          className="h-5 w-5 rounded border border-edge text-[11px] text-zinc-400 hover:border-accent hover:text-accent"
          aria-label={`decrease ${cat}`}
        >
          −
        </button>
        <button
          onClick={() => onSet(target + 1)}
          className="h-5 w-5 rounded border border-edge text-[11px] text-zinc-400 hover:border-accent hover:text-accent"
          aria-label={`increase ${cat}`}
        >
          +
        </button>
      </div>
    </div>
  );
}

/** One of the two facing "spell pages": a theme selector column. */
function ThemePage({
  side,
  value,
  onChange,
  themes,
}: {
  side: "A" | "B";
  value: string;
  onChange: (id: string) => void;
  themes: { id: string; label: string }[];
}) {
  return (
    <div className="flex-1">
      <p className="mb-1 font-display text-[11px] uppercase tracking-[0.2em] text-accent/80">
        Theme {side}
      </p>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        data-testid={`theme-select-${side.toLowerCase()}`}
        className="w-full rounded-md border border-accent/40 bg-ink/70 px-2 py-2 text-xs text-zinc-200
                   outline-none focus:border-accent focus:shadow-neon"
      >
        <option value="">— choose a theme —</option>
        {themes.map((t) => (
          <option key={t.id} value={t.id}>
            {t.label}
          </option>
        ))}
      </select>
    </div>
  );
}

export function TemplatePanel() {
  const { cards, basics, add } = useDeck();
  const {
    panelOpen,
    closePanel,
    templates,
    themes,
    selectedId,
    composite,
    setCount,
    setThemeA,
    setThemeB,
    setFreeText,
  } = useTemplateStore();

  const [shown, setShown] = useState(10);

  // The commander currently in the deck (themes are scoped to its colors).
  const commander: Card | null =
    Object.values(cards).find((dc) => dc.zone === "Commanders")?.card ?? null;

  const selected = templates.find((t) => t.id === selectedId);

  useEffect(() => {
    const key = (e: KeyboardEvent) => e.key === "Escape" && closePanel();
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [closePanel]);

  // Reset the visible page whenever the query inputs change.
  useEffect(() => {
    setShown(10);
  }, [commander?.id, composite.themeA, composite.themeB, composite.freeText]);

  const themesSel = [composite.themeA, composite.themeB].filter(Boolean);
  const hasQuery = themesSel.length > 0 || composite.freeText.trim().length > 0;

  const { data, isFetching } = useQuery({
    queryKey: [
      "theme-suggest",
      commander?.id,
      composite.themeA,
      composite.themeB,
      composite.freeText,
      shown,
    ],
    queryFn: () => themeSuggest(commander!.id, themesSel, composite.freeText, shown, 0),
    enabled: panelOpen && commander != null && hasQuery,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  });

  // Live deck counts per category to overlay on the target bars.
  const deckCounts = useMemo(() => {
    const c: Record<string, number> = {
      land: 0,
      ramp: 0,
      card_draw: 0,
      removal: 0,
      board_wipe: 0,
    };
    for (const dc of Object.values(cards)) {
      const cat = ZONE_TO_CAT[dc.zone];
      if (cat) c[cat] += 1;
    }
    for (const b of Object.values(basics)) c.land += b.quantity;
    return c;
  }, [cards, basics]);

  if (!panelOpen) return null;

  const counts = composite.counts;
  const quotaSum = TEMPLATE_CATEGORIES.reduce((s, c) => s + (counts[c] || 0), 0);
  const synergySlots = Math.max(0, 99 - quotaSum);
  const suggestions = data?.cards ?? [];

  return (
    <>
      <div className="fixed inset-0 z-[120] bg-black/50" onClick={closePanel} />
      <div
        className="fixed right-0 top-0 z-[125] flex h-screen w-[560px] flex-col border-l border-accent/30
                   bg-ink/90 shadow-neon backdrop-blur-md"
        data-testid="template-panel"
        style={{
          backgroundImage:
            "radial-gradient(620px 300px at 100% -10%, rgba(255,210,74,0.10), transparent)",
        }}
      >
        {/* Header */}
        <div className="flex items-start justify-between border-b border-accent/30 px-4 py-3">
          <div className="min-w-0">
            <p className="font-display text-[9px] uppercase tracking-wider text-accent">
              ⚜ Template
            </p>
            <p className="arcade-bevel mt-0.5 truncate text-sm">
              {selected?.name ?? "Simmander Composite"}
            </p>
            {selected && (
              <p className="mt-0.5 text-[10px] text-zinc-500">{selected.notes}</p>
            )}
          </div>
          <button
            onClick={closePanel}
            className="ml-2 rounded p-1 text-zinc-500 transition hover:bg-accent/10 hover:text-accent"
          >
            ✕
          </button>
        </div>

        <div className="flex-1 overflow-y-auto scrollbar-thin">
          {/* Composition targets */}
          <section className="border-b border-accent/30 px-4 py-3">
            <div className="mb-2 flex items-baseline justify-between">
              <p className="font-display text-[11px] uppercase tracking-[0.2em] text-accent">
                Composition
              </p>
              <p className="text-[10px] text-zinc-500">
                {quotaSum} quota + {synergySlots} synergy ·{" "}
                <span className="text-accent/70">commander 1</span>
              </p>
            </div>
            <div className="space-y-1.5">
              {TEMPLATE_CATEGORIES.map((cat) => (
                <CompositionBar
                  key={cat}
                  cat={cat}
                  target={counts[cat] || 0}
                  current={deckCounts[cat] || 0}
                  onSet={(n) => setCount(cat, n)}
                />
              ))}
            </div>
          </section>

          {/* Dual-theme: two facing spell pages with a gilded divider */}
          <section className="px-4 py-3">
            <p className="mb-2 font-display text-[11px] uppercase tracking-[0.2em] text-accent">
              Dual Theme
            </p>
            <div className="flex items-stretch gap-3">
              <ThemePage
                side="A"
                value={composite.themeA}
                onChange={setThemeA}
                themes={themes}
              />
              {/* gilded divider */}
              <div
                className="w-px shrink-0 self-stretch"
                style={{
                  background:
                    "linear-gradient(to bottom, transparent, rgba(255,210,74,0.6), transparent)",
                }}
              />
              <ThemePage
                side="B"
                value={composite.themeB}
                onChange={setThemeB}
                themes={themes}
              />
            </div>
            <input
              value={composite.freeText}
              onChange={(e) => setFreeText(e.target.value)}
              placeholder="Refine with free text — e.g. “lifegain tokens”"
              data-testid="theme-freetext"
              className="mt-2 w-full rounded-md border border-accent/40 bg-ink/70 px-3 py-2 text-xs
                         outline-none focus:border-accent focus:shadow-neon"
            />

            {/* Theme card grid */}
            <div className="mt-3">
              {!commander && (
                <p className="py-8 text-center text-xs text-zinc-500">
                  Add a commander to see in-color theme cards.
                </p>
              )}
              {commander && !hasQuery && (
                <p className="py-8 text-center text-xs text-zinc-500">
                  Pick a theme (or type free text) to see ranked cards for{" "}
                  <span className="text-accent">{commander.name}</span>.
                </p>
              )}
              {commander && hasQuery && (
                <>
                  <div
                    className="grid grid-cols-3 gap-2"
                    data-testid="theme-grid"
                  >
                    {suggestions.map((s, i) => (
                      <div
                        key={s.card.id}
                        className="tmpl-reveal relative"
                        style={{ animationDelay: `${Math.min(i, 12) * 35}ms` }}
                      >
                        <CardTile
                          card={s.card}
                          compact
                          badge={s.card.ier != null ? String(s.card.ier) : undefined}
                          onAdd={() => add(s.card)}
                        />
                        {s.themes_matched > 1 && (
                          <span
                            title="Bridges both themes"
                            className="absolute left-1 top-1 z-10 rounded bg-accent/90 px-1 text-[8px]
                                       font-bold text-ink shadow"
                          >
                            ⚜ both
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                  {suggestions.length === 0 && !isFetching && (
                    <p className="py-8 text-center text-xs text-zinc-500">
                      No in-color cards for this theme.
                    </p>
                  )}
                  {data?.has_more && (
                    <button
                      onClick={() => setShown((n) => n + 10)}
                      data-testid="theme-show-more"
                      className="mt-3 w-full rounded-lg border border-accent/40 py-2 text-[11px]
                                 font-semibold uppercase tracking-widest text-accent transition
                                 hover:bg-accent/10"
                    >
                      {isFetching ? "Loading…" : "Show 10 more"}
                    </button>
                  )}
                  {data && (
                    <p className="mt-2 text-center text-[10px] text-zinc-600">
                      showing {suggestions.length} of {data.total} · ranked by
                      efficiency × commander synergy
                    </p>
                  )}
                </>
              )}
            </div>
          </section>
        </div>
      </div>
    </>
  );
}
