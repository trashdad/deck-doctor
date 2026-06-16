"use client";

import { useEffect, useState } from "react";
import { importDeck } from "@/lib/api";
import { useDecksStore } from "@/store/decks";

const PLACEHOLDER = `Commander: The Ur-Dragon
1 Sol Ring
1 Command Tower
...paste a Moxfield / Archidekt / MTGO / Arena list`;

export function ImportExportDialog({
  isOpen,
  onClose,
}: {
  isOpen: boolean;
  onClose: () => void;
}) {
  const load = useDecksStore((s) => s.load);
  const [name, setName] = useState("Imported deck");
  const [text, setText] = useState("");
  const [unresolved, setUnresolved] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [onClose]);

  if (!isOpen) return null;

  async function handleImport() {
    setBusy(true);
    setError(null);
    setUnresolved(null);
    try {
      const result = await importDeck(text, name);
      await load(result.deck.id);
      if (result.unresolved.length > 0) {
        setUnresolved(result.unresolved);
      } else {
        onClose();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Import failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-[160] flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
      data-testid="import-dialog"
    >
      <div
        className="w-full max-w-xl rounded-xl border border-accent/50 bg-ink/90 p-4 shadow-neon backdrop-blur-md"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="arcade-bevel text-sm">Import decklist</h2>
          <span className="text-[10px] text-zinc-500">
            Moxfield / Archidekt / MTGO / Arena formats
          </span>
        </div>

        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="mb-2 w-full rounded border border-accent/40 bg-ink/70 px-2 py-1.5 text-xs text-zinc-200
                     outline-none focus:border-accent focus:shadow-neon"
        />
        <textarea
          data-testid="import-text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={PLACEHOLDER}
          className="h-64 w-full resize-none rounded border border-accent/40 bg-ink/70 p-2 font-mono
                     text-xs text-zinc-200 outline-none focus:border-accent focus:shadow-neon scrollbar-thin"
        />

        {unresolved && (
          <div className="mt-2 rounded border border-accent/40 bg-accent/10 p-2">
            <p className="text-[11px] font-semibold text-accent">
              {unresolved.length} line{unresolved.length === 1 ? "" : "s"} didn&apos;t resolve
              (deck still imported):
            </p>
            <ul className="mt-1 max-h-24 overflow-y-auto text-[10px] text-accent/80 scrollbar-thin">
              {unresolved.map((l, i) => (
                <li key={i}>{l}</li>
              ))}
            </ul>
            <button
              onClick={onClose}
              className="mt-2 rounded border border-accent/40 px-2 py-1 text-[10px] text-accent hover:bg-accent/10"
            >
              Done
            </button>
          </div>
        )}

        {error && <p className="mt-2 text-[11px] text-red-400">{error}</p>}

        <div className="mt-3 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-lg border border-accent/50 px-3 py-1.5 text-xs text-accent hover:bg-accent/10"
          >
            Cancel
          </button>
          <button
            data-testid="import-submit"
            onClick={handleImport}
            disabled={busy || !text.trim()}
            className={[
              "rounded-lg border px-3 py-1.5 text-xs font-semibold transition",
              busy || !text.trim()
                ? "cursor-not-allowed border-zinc-800 text-zinc-700"
                : "border-accent/50 text-accent hover:bg-accent/10",
            ].join(" ")}
          >
            {busy ? "Importing…" : "Import"}
          </button>
        </div>
      </div>
    </div>
  );
}
