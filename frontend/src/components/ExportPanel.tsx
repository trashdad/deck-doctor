"use client";

import { useEffect, useState } from "react";
import { exportDeck } from "@/lib/api";
import { manapoolAddDeckUrl } from "@/lib/affiliate";
import type { DeckEntry } from "@/lib/types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ExportPanelProps {
  isOpen: boolean;
  onClose: () => void;
  entries: DeckEntry[];
  commanderId: string | null;
}

type ExportFormat = "text" | "moxfield" | "archidekt" | "manapool";

interface FormatSpec {
  id: ExportFormat;
  label: string;
  fileName: string | null; // null = no download (ManaPool clipboard flow)
  description: string;
}

const FORMAT_SPECS: FormatSpec[] = [
  {
    id: "text",
    label: "Text",
    fileName: "deck.txt",
    description: "Plain-text decklist — paste anywhere or import back here.",
  },
  {
    id: "moxfield",
    label: "Moxfield CSV",
    fileName: "deck-moxfield.csv",
    description: "CSV ready to import into moxfield.com.",
  },
  {
    id: "archidekt",
    label: "Archidekt CSV",
    fileName: "deck-archidekt.csv",
    description: "CSV ready to import into archidekt.com (includes Category column).",
  },
  {
    id: "manapool",
    label: "Add all to cart",
    fileName: null,
    description: "Copies the decklist and opens ManaPool's mass-entry page.",
  },
];

// ---------------------------------------------------------------------------
// Download helper
// ---------------------------------------------------------------------------

function triggerDownload(content: string, fileName: string, mimeType = "text/plain") {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// Export panel
// ---------------------------------------------------------------------------

export function ExportPanel({ isOpen, onClose, entries, commanderId }: ExportPanelProps) {
  const [busy, setBusy] = useState<ExportFormat | null>(null);
  const [copied, setCopied] = useState<ExportFormat | null>(null);
  const [manapoolConfirm, setManapoolConfirm] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Close on Escape
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [onClose]);

  // Reset transient state when panel opens/closes
  useEffect(() => {
    if (!isOpen) {
      setBusy(null);
      setCopied(null);
      setManapoolConfirm(false);
      setError(null);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  // ---------------------------------------------------------------------------
  // Action handlers
  // ---------------------------------------------------------------------------

  async function handleDownload(spec: FormatSpec) {
    if (!spec.fileName) return;
    setBusy(spec.id);
    setError(null);
    try {
      const text = await exportDeck(entries, commanderId, spec.id);
      const mime = spec.fileName.endsWith(".csv") ? "text/csv" : "text/plain";
      triggerDownload(text, spec.fileName, mime);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setBusy(null);
    }
  }

  async function handleCopy(spec: FormatSpec) {
    if (!spec.fileName) return;
    setBusy(spec.id);
    setError(null);
    try {
      const text = await exportDeck(entries, commanderId, spec.id);
      await navigator.clipboard.writeText(text);
      setCopied(spec.id);
      setTimeout(() => setCopied(null), 2000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Copy failed");
    } finally {
      setBusy(null);
    }
  }

  async function handleManaPool() {
    setBusy("manapool");
    setError(null);
    setManapoolConfirm(false);
    try {
      const text = await exportDeck(entries, commanderId, "manapool");
      await navigator.clipboard.writeText(text);
      window.open(manapoolAddDeckUrl(), "_blank", "noopener,noreferrer");
      setManapoolConfirm(true);
      // Auto-hide the confirmation after 6 seconds
      setTimeout(() => setManapoolConfirm(false), 6000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "ManaPool handoff failed");
    } finally {
      setBusy(null);
    }
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-[120] bg-black/40" onClick={onClose} />

      {/* Panel */}
      <div
        className="fixed right-0 top-0 z-[125] flex h-screen w-[400px] flex-col
                   border-l border-edge bg-panel shadow-2xl"
        data-testid="export-panel"
      >
        {/* ── Header ───────────────────────────────────────────── */}
        <div className="flex items-start justify-between border-b border-edge px-4 py-3">
          <div>
            <p className="text-[9px] uppercase tracking-widest text-zinc-600">Export</p>
            <p className="text-sm font-semibold text-accent">Download or share your deck</p>
          </div>
          <button
            onClick={onClose}
            className="ml-2 mt-0.5 rounded p-1 text-zinc-500 transition hover:bg-zinc-700 hover:text-zinc-200"
            aria-label="Close export panel"
          >
            ✕
          </button>
        </div>

        {/* ── Body ─────────────────────────────────────────────── */}
        <div className="flex-1 overflow-y-auto scrollbar-thin px-4 py-4 space-y-4">
          {error && (
            <p className="rounded border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-400">
              {error}
            </p>
          )}

          {manapoolConfirm && (
            <div className="rounded border border-accent/40 bg-accent/10 px-3 py-2 text-xs text-accent">
              Decklist copied — paste it into ManaPool&apos;s mass-entry box.
            </div>
          )}

          {FORMAT_SPECS.map((spec) => {
            const isManaPool = spec.id === "manapool";
            const isBusy = busy === spec.id;
            const isCopied = copied === spec.id;

            return (
              <div
                key={spec.id}
                className="rounded-lg border border-edge bg-ink p-3 space-y-2"
              >
                <div>
                  <p className="text-xs font-semibold text-zinc-200">{spec.label}</p>
                  <p className="text-[10px] text-zinc-500">{spec.description}</p>
                </div>

                {isManaPool ? (
                  /* ManaPool: single "Add all to cart" button */
                  <button
                    onClick={() => void handleManaPool()}
                    disabled={isBusy}
                    className={[
                      "w-full rounded-md border px-3 py-2 text-xs font-semibold transition",
                      isBusy
                        ? "cursor-not-allowed border-zinc-700 text-zinc-600"
                        : "border-accent/60 text-accent hover:bg-accent/15",
                    ].join(" ")}
                  >
                    {isBusy ? "Opening ManaPool…" : "🛒 Add all to cart"}
                  </button>
                ) : (
                  /* Text / CSV: Download + Copy row */
                  <div className="flex gap-2">
                    <button
                      onClick={() => void handleDownload(spec)}
                      disabled={isBusy}
                      className={[
                        "flex-1 rounded-md border px-3 py-1.5 text-xs font-semibold transition",
                        isBusy
                          ? "cursor-not-allowed border-zinc-700 text-zinc-600"
                          : "border-accent/50 text-accent hover:bg-accent/10",
                      ].join(" ")}
                    >
                      {isBusy ? "Exporting…" : "⬇ Download"}
                    </button>
                    <button
                      onClick={() => void handleCopy(spec)}
                      disabled={isBusy}
                      className={[
                        "rounded-md border px-3 py-1.5 text-xs font-semibold transition",
                        isCopied
                          ? "border-accent bg-accent/20 text-accent"
                          : isBusy
                            ? "cursor-not-allowed border-zinc-700 text-zinc-600"
                            : "border-zinc-600 text-zinc-400 hover:border-accent/50 hover:text-accent",
                      ].join(" ")}
                    >
                      {isCopied ? "✓ Copied" : "Copy"}
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* ── Footer ───────────────────────────────────────────── */}
        <div className="border-t border-edge px-4 py-2 text-[10px] text-zinc-500">
          {entries.length} card{entries.length !== 1 ? "s" : ""} · formats: text, Moxfield CSV, Archidekt CSV, ManaPool
        </div>
      </div>
    </>
  );
}
