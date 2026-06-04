"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { searchCards } from "@/lib/api";
import type { Card } from "@/lib/types";
import { CardTile } from "./CardTile";

const COLORS = ["W", "U", "B", "R", "G"] as const;

export function SearchPanel({ onAdd }: { onAdd: (card: Card) => void }) {
  const [q, setQ] = useState("");
  const [colors, setColors] = useState<string[]>([]);
  const [type, setType] = useState("");

  const { data, isLoading, error } = useQuery({
    queryKey: ["cards", q, colors, type],
    queryFn: () => searchCards({ q, colors: colors.join(""), type }),
  });

  return (
    <section className="flex w-80 shrink-0 flex-col border-r border-edge bg-panel/60">
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
                  ? ({ W: "#f8f5e3", U: "#3b82f6", B: "#5b4a63", R: "#ef4444", G: "#22c55e" } as Record<string, string>)[c]
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
            className="ml-1 w-20 flex-1 rounded-md border border-edge bg-ink px-2 py-1 text-xs outline-none focus:border-accent"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 overflow-y-auto p-3 scrollbar-thin">
        {isLoading && <p className="col-span-2 text-xs text-zinc-500">Searching…</p>}
        {error && (
          <p className="col-span-2 text-xs text-red-400">
            API unreachable — start the backend on :8000.
          </p>
        )}
        {data?.map((card) => (
          <CardTile key={card.id} card={card} compact onClick={() => onAdd(card)} />
        ))}
        {data?.length === 0 && (
          <p className="col-span-2 text-xs text-zinc-600">No matches.</p>
        )}
      </div>
    </section>
  );
}
