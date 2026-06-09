"use client";

import { useState, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { searchCards, getCommanders } from "@/lib/api";
import type { Card } from "@/lib/types";
import { CardTile } from "./CardTile";
import { CardMenu } from "./CardMenu";

const COLORS = ["W", "U", "B", "R", "G"] as const;
type Tab = "search" | "commanders";

function CardWithMenu({
  card,
  onAdd,
}: {
  card: Card;
  onAdd: (card: Card) => void;
}) {
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null);

  const handleClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setMenu({ x: e.clientX, y: e.clientY });
  }, []);

  return (
    <>
      <div onClick={handleClick}>
        <CardTile card={card} compact />
      </div>
      {menu && (
        <CardMenu
          card={card}
          anchor={menu}
          onClose={() => setMenu(null)}
          // No onRemove — search panel cards aren't in the deck yet.
          // We add the card via the context menu in future; for now clicking the
          // tile directly adds it. Here just show SIMILAR CARDS.
        />
      )}
    </>
  );
}

export function SearchPanel({ onAdd }: { onAdd: (card: Card) => void }) {
  const [tab, setTab] = useState<Tab>("search");
  const [q, setQ] = useState("");
  const [colors, setColors] = useState<string[]>([]);
  const [type, setType] = useState("");
  const [cmdQ, setCmdQ] = useState("");

  const searchQuery = useQuery({
    queryKey: ["cards", q, colors, type],
    queryFn: () => searchCards({ q, colors: colors.join(""), type }),
    enabled: tab === "search",
  });

  const commandersQuery = useQuery({
    queryKey: ["commanders"],
    queryFn: getCommanders,
    staleTime: Infinity,
    enabled: tab === "commanders",
  });

  const commandersList = commandersQuery.data ?? [];
  const filteredCommanders = cmdQ.trim()
    ? commandersList.filter((c) =>
        c.name.toLowerCase().includes(cmdQ.toLowerCase()),
      )
    : commandersList;

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
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search cards…"
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
          <div className="border-b border-edge p-3">
            <input
              value={cmdQ}
              onChange={(e) => setCmdQ(e.target.value)}
              placeholder="Filter commanders…"
              className="w-full rounded-md border border-edge bg-ink px-3 py-2 text-sm
                         outline-none focus:border-accent"
            />
            {commandersList.length > 0 && (
              <p className="mt-1 text-[10px] text-zinc-600">
                {filteredCommanders.length} of {commandersList.length} commanders
              </p>
            )}
          </div>

          <div className="grid grid-cols-2 gap-2 overflow-y-auto p-3 scrollbar-thin">
            {commandersQuery.isLoading && (
              <p className="col-span-2 text-xs text-zinc-500">Loading commanders…</p>
            )}
            {filteredCommanders.map((card) => (
              <div
                key={card.id}
                onClick={() => onAdd(card)}
                className="cursor-pointer"
              >
                <CardTile card={card} compact />
              </div>
            ))}
            {!commandersQuery.isLoading && filteredCommanders.length === 0 && (
              <p className="col-span-2 text-xs text-zinc-600">No commanders found.</p>
            )}
          </div>
        </>
      )}
    </section>
  );
}
