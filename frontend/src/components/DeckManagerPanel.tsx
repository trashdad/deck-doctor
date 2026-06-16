"use client";

import { useEffect, useState } from "react";
import { useDecksStore } from "@/store/decks";
import { exportDeckUrl } from "@/lib/api";
import { useAuth } from "@/store/auth";

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  const secs = Math.max(0, (Date.now() - then) / 1000);
  if (secs < 60) return "just now";
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}

export function DeckManagerPanel({
  isOpen,
  onClose,
  onOpenImport,
}: {
  isOpen: boolean;
  onClose: () => void;
  onOpenImport: () => void;
}) {
  const { deckList, currentId, currentName, refresh, saveCurrent, load, remove } =
    useDecksStore();
  const user = useAuth((s) => s.user);
  const [name, setName] = useState(currentName);

  useEffect(() => {
    if (isOpen && user) void refresh();
  }, [isOpen, refresh, user]);

  useEffect(() => setName(currentName), [currentName]);

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [onClose]);

  if (!isOpen) return null;

  async function handleExport() {
    if (!currentId) return;
    const text = await fetch(exportDeckUrl(currentId), { credentials: "include" }).then((r) => r.text());
    const blob = new Blob([text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${currentName || "deck"}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <>
      <div className="fixed inset-0 z-[110] bg-black/40" onClick={onClose} />
      <div
        className="fixed right-0 top-0 z-[115] flex h-screen w-[460px] flex-col
                   border-l border-accent/30 bg-ink/90 shadow-neon backdrop-blur-md"
        data-testid="deck-manager-panel"
      >
        <div className="flex items-start justify-between border-b border-accent/30 px-4 py-3">
          <div>
            <p className="font-display text-[9px] uppercase tracking-wider text-accent">My Decks</p>
            <p className="text-sm font-semibold text-zinc-100">Saved decks</p>
          </div>
          <button
            onClick={onClose}
            className="rounded p-1 text-zinc-500 transition hover:bg-accent/10 hover:text-accent"
          >
            ✕
          </button>
        </div>

        {!user ? (
          <div className="flex-1 px-4 py-10 text-center text-xs text-zinc-500">
            Log in to save decks to your account.
            <br />
            (Your current deck still autosaves in this browser.)
          </div>
        ) : (
          <>
            {/* Save row */}
            <div className="flex items-center gap-2 border-b border-accent/30 px-4 py-3">
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Deck name"
                className="flex-1 rounded border border-accent/40 bg-ink/70 px-2 py-1.5 text-xs text-zinc-200
                           outline-none focus:border-accent focus:shadow-neon"
              />
              <button
                data-testid="deck-save"
                onClick={() => void saveCurrent(name)}
                className="rounded-lg border border-accent/50 px-3 py-1.5 text-xs font-semibold
                           text-accent transition hover:bg-accent/10"
              >
                {currentId ? "Save" : "Save as…"}
              </button>
            </div>

            {/* Deck list */}
            <div className="flex-1 overflow-y-auto scrollbar-thin">
              {deckList.length === 0 && (
                <p className="px-4 py-10 text-center text-xs text-zinc-500">
                  No saved decks yet. Build a deck and hit Save.
                </p>
              )}
              <ul className="divide-y divide-accent/10">
                {deckList.map((d) => (
                  <li
                    key={d.id}
                    data-testid="deck-row"
                    className={[
                      "flex items-center gap-2 px-4 py-2.5 transition hover:bg-accent/[0.06] hover:shadow-neon",
                      d.id === currentId ? "border-l-2 border-accent bg-accent/5" : "",
                    ].join(" ")}
                  >
                    <button
                      className="min-w-0 flex-1 text-left"
                      onClick={() => {
                        void load(d.id);
                        onClose();
                      }}
                    >
                      <p className="truncate text-xs font-semibold text-zinc-200">{d.name}</p>
                      <p className="text-[10px] text-zinc-500">
                        {d.card_count} cards · {relativeTime(d.updated_at)}
                      </p>
                    </button>
                    <button
                      title="Delete"
                      onClick={() => {
                        if (window.confirm(`Delete "${d.name}"?`)) void remove(d.id);
                      }}
                      className="shrink-0 rounded p-1 text-zinc-600 transition hover:bg-red-500/10 hover:text-red-400"
                    >
                      🗑
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </>
        )}

        {/* Footer actions */}
        <div className="flex gap-2 border-t border-accent/30 px-4 py-3">
          <button
            onClick={onOpenImport}
            className="flex-1 rounded-lg border border-accent/50 px-3 py-2 text-xs font-semibold
                       text-accent transition hover:bg-accent/10"
          >
            Import…
          </button>
          <button
            onClick={handleExport}
            disabled={!currentId}
            className={[
              "flex-1 rounded-lg border px-3 py-2 text-xs font-semibold transition",
              currentId
                ? "border-accent/50 text-accent hover:bg-accent/10"
                : "cursor-not-allowed border-zinc-800 text-zinc-700",
            ].join(" ")}
          >
            Export
          </button>
        </div>
      </div>
    </>
  );
}
