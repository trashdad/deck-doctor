"use client";

import { useState, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { searchCards, getCommanders } from "@/lib/api";
import type { Card, CommanderSort } from "@/lib/types";
import { useDeck, commanderIdentity, withinIdentity } from "@/store/deck";
import { isValidPartner } from "@/lib/partners";
import { useUI } from "@/store/ui";
import { CardTile } from "./CardTile";
import { CardMenu } from "./CardMenu";

const COLORS = ["W", "U", "B", "R", "G"] as const;
const COLOR_BG: Record<string, string> = {
  W: "#f8f5e3",
  U: "#3b82f6",
  B: "#5b4a63",
  R: "#ef4444",
  G: "#22c55e",
};
const SORT_LABELS: Record<CommanderSort, string> = {
  popularity: "Most played",
  name: "Name (A–Z)",
  ier: "Efficiency (IER)",
};
type Tab = "search" | "commanders";

/** Compact deck-count label: 1240 → "1.2k". */
function fmtCount(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n);
}

function CardWithMenu({
  card,
  onAdd,
}: {
  card: Card;
  onAdd: (card: Card) => void;
}) {
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null);
  const deckCards = useDeck((s) => s.cards);
  // Once a commander is set, off-color cards are illegal and can't be added.
  const ci = commanderIdentity(deckCards);
  const offColor = ci.size > 0 && !withinIdentity(ci, card);

  const handleClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setMenu({ x: e.clientX, y: e.clientY });
  }, []);

  // Right-click also opens the same menu (Archidekt-style); suppress the
  // browser's native context menu.
  const handleContextMenu = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setMenu({ x: e.clientX, y: e.clientY });
  }, []);

  const handleAdd = useCallback(() => {
    onAdd(card);
  }, [onAdd, card]);

  return (
    <>
      {/*
        Click the tile art/name for the tag/similar menu.
        The `onAdd` prop is passed into CardTile's built-in action bar so
        the button lives INSIDE the card element — no cross-element hover gap
        that caused the flicker. For off-color cards we pass no onAdd so the
        action bar is absent; we show an off-color badge instead via a wrapper.
      */}
      <div
        className={`relative ${offColor ? "opacity-45 grayscale" : ""}`}
        onClick={handleClick}
        onContextMenu={handleContextMenu}
      >
        {offColor ? (
          // Off-color: no add action, just a visual warning on hover.
          <div className="group">
            <CardTile card={card} compact />
            <div
              title="Outside your commander's color identity"
              className="pointer-events-none absolute inset-x-1 bottom-1 z-20 rounded-md bg-red-900/85 py-1
                         text-center text-[10px] font-bold uppercase tracking-widest text-red-200
                         opacity-0 shadow-lg transition group-hover:opacity-100"
            >
              ⊘ Off-color
            </div>
          </div>
        ) : (
          // Normal: the CardTile action bar contains the ＋ button — no flicker.
          <CardTile
            card={card}
            compact
            onAdd={handleAdd}
          />
        )}
      </div>
      {menu && (
        <CardMenu
          card={card}
          anchor={menu}
          onClose={() => setMenu(null)}
          // No onRemove — search-panel cards aren't in the deck yet.
        />
      )}
    </>
  );
}

export function SearchPanel({ onAdd }: { onAdd: (card: Card) => void }) {
  const tab = useUI((s) => s.searchTab);
  const setTab = useUI((s) => s.setSearchTab);
  const partnerPick = useUI((s) => s.partnerPick);
  const setPartnerPick = useUI((s) => s.setPartnerPick);
  const setCommander = useDeck((s) => s.setCommander);
  const deckCards = useDeck((s) => s.cards);
  const existingCommander =
    Object.values(deckCards).find((dc) => dc.zone === "Commanders")?.card ?? null;
  // Picking from the commander list: in partner-pick mode add a (validated)
  // second commander; otherwise set/replace the primary commander.
  const pickCommander = (card: Card) => {
    if (partnerPick) {
      setCommander(card, true);
      setPartnerPick(false);
    } else {
      setCommander(card, false);
    }
    // Jump to the card search (now ranked for this commander) to build the 99.
    setTab("search");
  };
  const [q, setQ] = useState("");
  // Scryfall-style: search the card NAME or its ORACLE TEXT.
  const [searchField, setSearchField] = useState<"name" | "oracle">("name");
  const [colors, setColors] = useState<string[]>([]);
  const [type, setType] = useState("");
  const [cmdQ, setCmdQ] = useState("");
  const [cmdColors, setCmdColors] = useState<string[]>([]);
  // Default the commander list to the most-popular commanders, highest first.
  const [cmdSort, setCmdSort] = useState<CommanderSort>("popularity");

  const searchQuery = useQuery({
    queryKey: ["cards", q, searchField, colors, type, existingCommander?.id ?? ""],
    queryFn: () =>
      searchCards({
        q: searchField === "name" ? q : "",
        oracle: searchField === "oracle" ? q : "",
        colors: colors.join(""),
        type,
        commander_id: existingCommander?.id,
      }),
    enabled: tab === "search",
  });

  // Server sorts (popularity/name/ier) + filters by color identity; the free-text
  // box filters the returned list instantly client-side (no refetch per keystroke).
  const commandersQuery = useQuery({
    queryKey: ["commanders", cmdColors, cmdSort],
    queryFn: () => getCommanders({ colors: cmdColors.join(""), sort: cmdSort }),
    staleTime: 60_000,
    enabled: tab === "commanders",
  });

  const commandersList = commandersQuery.data ?? [];
  let filteredCommanders = cmdQ.trim()
    ? commandersList.filter((c) =>
        c.name.toLowerCase().includes(cmdQ.toLowerCase()),
      )
    : commandersList;
  // While choosing a partner, only show cards that legally pair with the commander.
  if (partnerPick && existingCommander) {
    filteredCommanders = filteredCommanders.filter((c) =>
      isValidPartner(c, existingCommander),
    );
  }

  return (
    <section className="flex w-80 shrink-0 flex-col border-r border-edge bg-panel/60">
      {/* Tabs */}
      <div className="flex border-b border-edge">
        {(["search", "commanders"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={[
              "flex-1 py-2 text-[10px] font-bold uppercase tracking-widest transition",
              tab === t
                ? "border-b-2 border-accent text-accent"
                : "text-zinc-500 hover:text-zinc-300",
            ].join(" ")}
          >
            {t === "search" ? "Search" : "Commanders"}
          </button>
        ))}
      </div>

      {tab === "search" ? (
        <>
          <div className="space-y-2 border-b border-edge p-3">
            {/* Scryfall-style field toggle: search by card name or by oracle text. */}
            <div className="flex overflow-hidden rounded-md border border-edge text-[10px] font-bold uppercase tracking-wider">
              {(["name", "oracle"] as const).map((f) => (
                <button
                  key={f}
                  onClick={() => setSearchField(f)}
                  data-testid={`search-field-${f}`}
                  className={`flex-1 py-1.5 transition ${
                    searchField === f
                      ? "bg-accent/20 text-accent"
                      : "text-zinc-500 hover:text-zinc-300"
                  }`}
                >
                  {f === "name" ? "Card name" : "Oracle text"}
                </button>
              ))}
            </div>
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => {
                // Enter adds the FIRST search result to the deck (Moxfield-style
                // quick-add), then clears the box for the next search. Guarded
                // against an empty result set.
                if (e.key !== "Enter") return;
                const first = searchQuery.data?.[0];
                if (!first) return;
                e.preventDefault();
                onAdd(first);
                setQ("");
              }}
              placeholder={
                searchField === "name" ? "Search by card name…" : "Search oracle text… (e.g. \"draw a card\")"
              }
              className="w-full rounded-md border border-edge bg-ink px-3 py-2 text-sm
                         outline-none focus:border-accent"
            />
            <div className="flex items-center gap-1">
              {COLORS.map((c) => (
                <button
                  key={c}
                  onClick={() =>
                    setColors((cur) =>
                      cur.includes(c) ? cur.filter((x) => x !== c) : [...cur, c],
                    )
                  }
                  className={`h-7 w-7 rounded-full border text-xs font-bold transition ${
                    colors.includes(c)
                      ? "border-accent text-ink"
                      : "border-edge text-zinc-400"
                  }`}
                  style={{
                    background: colors.includes(c)
                      ? (
                          {
                            W: "#f8f5e3",
                            U: "#3b82f6",
                            B: "#5b4a63",
                            R: "#ef4444",
                            G: "#22c55e",
                          } as Record<string, string>
                        )[c]
                      : "transparent",
                  }}
                >
                  {c}
                </button>
              ))}
              <input
                value={type}
                onChange={(e) => setType(e.target.value)}
                placeholder="type…"
                className="ml-1 w-20 flex-1 rounded-md border border-edge bg-ink px-2 py-1
                           text-xs outline-none focus:border-accent"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2 overflow-y-auto p-3 scrollbar-thin">
            {searchQuery.isLoading && (
              <p className="col-span-2 text-xs text-zinc-500">Searching…</p>
            )}
            {searchQuery.error && (
              <p className="col-span-2 text-xs text-red-400">
                API unreachable — start the backend on :8001.
              </p>
            )}
            {searchQuery.data?.map((card) => (
              <CardWithMenu key={card.id} card={card} onAdd={onAdd} />
            ))}
            {searchQuery.data?.length === 0 && (
              <p className="col-span-2 text-xs text-zinc-600">No matches.</p>
            )}
          </div>
        </>
      ) : (
        <>
          <div className="space-y-2 border-b border-edge p-3">
            <input
              value={cmdQ}
              onChange={(e) => setCmdQ(e.target.value)}
              placeholder="Search commanders…"
              className="w-full rounded-md border border-edge bg-ink px-3 py-2 text-sm
                         outline-none focus:border-accent"
            />
            <div className="flex items-center gap-1">
              {COLORS.map((c) => (
                <button
                  key={c}
                  onClick={() =>
                    setCmdColors((cur) =>
                      cur.includes(c) ? cur.filter((x) => x !== c) : [...cur, c],
                    )
                  }
                  className={`h-7 w-7 rounded-full border text-xs font-bold transition ${
                    cmdColors.includes(c)
                      ? "border-accent text-ink"
                      : "border-edge text-zinc-400"
                  }`}
                  style={{
                    background: cmdColors.includes(c) ? COLOR_BG[c] : "transparent",
                  }}
                >
                  {c}
                </button>
              ))}
              <select
                value={cmdSort}
                onChange={(e) => setCmdSort(e.target.value as CommanderSort)}
                className="ml-auto rounded-md border border-edge bg-ink px-2 py-1.5 text-[11px]
                           text-zinc-300 outline-none focus:border-accent"
                title="Sort commanders"
              >
                {(Object.keys(SORT_LABELS) as CommanderSort[]).map((s) => (
                  <option key={s} value={s}>
                    {SORT_LABELS[s]}
                  </option>
                ))}
              </select>
            </div>
            {commandersList.length > 0 && (
              <p className="text-[10px] text-zinc-600">
                {filteredCommanders.length} of {commandersList.length} commanders
                {cmdSort === "popularity" && " · by deck count"}
              </p>
            )}
          </div>

          {partnerPick && existingCommander && (
            <div className="flex items-center justify-between gap-2 border-b border-accent/30 bg-accent/10 px-3 py-2">
              <span className="text-[11px] text-accent">
                Pick a valid partner for{" "}
                <span className="font-semibold">{existingCommander.name}</span>
              </span>
              <button
                onClick={() => setPartnerPick(false)}
                className="shrink-0 rounded border border-edge px-1.5 py-0.5 text-[10px] text-zinc-400
                           transition hover:text-zinc-200"
              >
                Cancel
              </button>
            </div>
          )}

          <div className="grid grid-cols-2 gap-2 overflow-y-auto p-3 scrollbar-thin">
            {commandersQuery.isLoading && (
              <p className="col-span-2 text-xs text-zinc-500">Loading commanders…</p>
            )}
            {partnerPick && existingCommander && filteredCommanders.length === 0 && (
              <p className="col-span-2 text-xs italic text-zinc-600">
                No legal partners for {existingCommander.name} in the list.
              </p>
            )}
            {filteredCommanders.map((card) => {
              const decks = card.deck_count ?? 0;
              return (
                <div
                  key={card.id}
                  onClick={() => pickCommander(card)}
                  className="cursor-pointer"
                  data-testid="commander-tile"
                >
                  <CardTile
                    card={card}
                    compact
                    badge={decks > 0 ? `▲ ${fmtCount(decks)}` : undefined}
                  />
                  <p className="mt-0.5 flex items-baseline justify-between px-0.5 text-[9px] leading-tight">
                    <span className="truncate text-zinc-500" title={card.name}>
                      {decks > 0 ? `${decks.toLocaleString()} decks` : "—"}
                    </span>
                    {card.ier != null && (
                      <span className="shrink-0 font-semibold text-accent/70">
                        {card.ier}
                      </span>
                    )}
                  </p>
                </div>
              );
            })}
            {!commandersQuery.isLoading && filteredCommanders.length === 0 && (
              <p className="col-span-2 text-xs text-zinc-600">No commanders found.</p>
            )}
          </div>
        </>
      )}
    </section>
  );
}
