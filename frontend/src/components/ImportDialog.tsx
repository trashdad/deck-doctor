"use client";

/**
 * ImportDialog — working-deck importer with error-deconfliction.
 *
 * Flow:
 *  1. User pastes a Moxfield / Archidekt / MTGO / Arena decklist.
 *  2. "Parse list" calls POST /deck/parse-import (no auth).
 *  3. Summary shows resolved count + unresolved count.
 *  4. For each unresolved line, up to 5 suggestion chips + "Skip" are shown.
 *     The user MUST handle every unresolved line before importing.
 *  5. "Import to deck" calls useDeck.loadImported() and closes.
 */

import { useEffect, useState } from "react";
import { parseImport, type ParseImportResolved, type ParseImportUnresolved } from "@/lib/api";
import { useDeck } from "@/store/deck";
import { autoZone, type Zone } from "@/lib/zones";
import type { Card } from "@/lib/types";

const PLACEHOLDER = `Commander: The Ur-Dragon
1 Sol Ring
1 Command Tower
37 Forest
...paste a Moxfield or Archidekt list`;

/** Resolution for one unresolved line: a card id or the sentinel "skip". */
type LineChoice = string | "skip";

export function ImportDialog({
  isOpen,
  onClose,
}: {
  isOpen: boolean;
  onClose: () => void;
}) {
  const loadImported = useDeck((s) => s.loadImported);

  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Parse results
  const [resolved, setResolved] = useState<ParseImportResolved[]>([]);
  const [unresolved, setUnresolved] = useState<ParseImportUnresolved[]>([]);
  const [commanderId, setCommanderId] = useState<string | null>(null);
  const [parsed, setParsed] = useState(false);

  // Per-unresolved-line choices: index -> LineChoice
  const [choices, setChoices] = useState<Record<number, LineChoice>>({});

  // Escape key closes
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  if (!isOpen) return null;

  // Reset state when dialog opens
  function reset() {
    setText("");
    setBusy(false);
    setError(null);
    setResolved([]);
    setUnresolved([]);
    setCommanderId(null);
    setParsed(false);
    setChoices({});
  }

  function handleClose() {
    reset();
    onClose();
  }

  async function handleParse() {
    setBusy(true);
    setError(null);
    setParsed(false);
    setChoices({});
    try {
      const result = await parseImport(text);
      setResolved(result.resolved);
      setUnresolved(result.unresolved);
      setCommanderId(result.commander_id);
      setParsed(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Parse failed");
    } finally {
      setBusy(false);
    }
  }

  function handleChoose(idx: number, choice: LineChoice) {
    setChoices((prev) => ({ ...prev, [idx]: choice }));
  }

  // All unresolved lines must have a choice before import is allowed
  const allHandled =
    parsed && unresolved.every((_, i) => choices[i] !== undefined);

  // Count how many cards will import (resolved + accepted suggestions, counting basic quantities)
  const willImport: number = (() => {
    let count = resolved.reduce((sum, r) => sum + r.quantity, 0);
    unresolved.forEach((entry, i) => {
      const choice = choices[i];
      if (choice && choice !== "skip") {
        count += entry.quantity;
      }
    });
    return count;
  })();

  function handleImport() {
    // Build the final row list
    const rows: { card: Card; zone: Zone; quantity: number }[] = [];

    // Add resolved rows
    for (const r of resolved) {
      rows.push({ card: r.card, zone: r.zone as Zone, quantity: r.quantity });
    }

    // Add user-picked suggestions
    for (let i = 0; i < unresolved.length; i++) {
      const choice = choices[i];
      if (!choice || choice === "skip") continue;
      const entry = unresolved[i];
      const suggCard = entry.suggestions.find((s) => s.id === choice);
      if (!suggCard) continue;
      // Derive zone: use autoZone on the client (same logic as adding a card normally)
      const zone: Zone =
        entry.line.toLowerCase().startsWith("commander:")
          ? "Commanders"
          : autoZone(suggCard);
      rows.push({ card: suggCard, zone, quantity: entry.quantity });
    }

    loadImported(rows, true);
    handleClose();
  }

  return (
    <div
      className="fixed inset-0 z-[160] flex items-center justify-center bg-black/70 p-4"
      onClick={handleClose}
      data-testid="import-dialog"
    >
      <div
        className="flex max-h-[90vh] w-full max-w-xl flex-col rounded-2xl border border-accent/50
                   bg-ink/90 shadow-neon backdrop-blur-md"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-accent/30 px-5 py-4">
          <div>
            <p className="arcade-bevel text-sm">
              Import Decklist
            </p>
            <p className="text-[10px] uppercase tracking-widest text-zinc-500">
              Moxfield · Archidekt
            </p>
          </div>
          <button
            onClick={handleClose}
            className="rounded-lg px-2 py-1 text-xs text-zinc-500 hover:text-accent"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto px-5 py-4 scrollbar-thin">
          {/* Textarea */}
          <textarea
            data-testid="import-text"
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              if (parsed) setParsed(false);
            }}
            placeholder={PLACEHOLDER}
            className="h-44 w-full resize-none rounded-lg border border-accent/40 bg-ink/70 p-3
                       font-mono text-xs text-zinc-200 outline-none focus:border-accent focus:shadow-neon
                       scrollbar-thin"
          />

          {/* Parse button */}
          <div className="mt-3 flex justify-end">
            <button
              data-testid="parse-list-btn"
              onClick={handleParse}
              disabled={busy || !text.trim()}
              className={[
                "rounded-lg border px-4 py-2 text-xs font-semibold transition",
                busy || !text.trim()
                  ? "cursor-not-allowed border-zinc-800 text-zinc-600"
                  : "border-accent/50 text-accent hover:bg-accent/10",
              ].join(" ")}
            >
              {busy ? "Parsing…" : "Parse list"}
            </button>
          </div>

          {/* Error */}
          {error && (
            <p className="mt-2 text-[11px] text-red-400">{error}</p>
          )}

          {/* Results summary */}
          {parsed && (
            <div className="mt-4 space-y-4">
              <div className="rounded-lg border border-edge bg-panel2/60 px-4 py-3">
                <p className="text-xs text-zinc-300">
                  <span className="font-semibold text-emerald-400">
                    ✓ {resolved.length} card{resolved.length !== 1 ? "s" : ""} matched
                  </span>
                  {unresolved.length > 0 && (
                    <>
                      {" · "}
                      <span className="font-semibold text-accent">
                        {unresolved.length} need{unresolved.length === 1 ? "s" : ""} your attention
                      </span>
                    </>
                  )}
                </p>
              </div>

              {/* Deconfliction list */}
              {unresolved.length > 0 && (
                <div className="space-y-3">
                  <p className="font-display text-[9px] uppercase tracking-wider text-accent">
                    Fix unresolved lines
                  </p>
                  {unresolved.map((entry, i) => (
                    <DeconflictRow
                      key={i}
                      entry={entry}
                      choice={choices[i]}
                      onChoose={(c) => handleChoose(i, c)}
                    />
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        {parsed && (
          <div className="flex items-center justify-between border-t border-accent/30 px-5 py-3">
            <p className="text-[11px] text-zinc-400">
              <span className="font-semibold text-zinc-200">{willImport}</span> card
              {willImport !== 1 ? "s" : ""} will import
            </p>
            <div className="flex gap-2">
              <button
                onClick={handleClose}
                className="rounded-lg border border-accent/50 px-3 py-1.5 text-xs text-accent
                           hover:bg-accent/10"
              >
                Cancel
              </button>
              <button
                data-testid="import-to-deck-btn"
                onClick={handleImport}
                disabled={!allHandled}
                title={!allHandled ? "Resolve or skip all unresolved lines first" : undefined}
                className={[
                  "rounded-lg border px-4 py-1.5 text-xs font-semibold transition",
                  !allHandled
                    ? "cursor-not-allowed border-zinc-800 text-zinc-600"
                    : "border-accent/50 text-accent hover:bg-accent/10",
                ].join(" ")}
              >
                Import to deck
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-component: one unresolved row with suggestion chips
// ---------------------------------------------------------------------------

function DeconflictRow({
  entry,
  choice,
  onChoose,
}: {
  entry: ParseImportUnresolved;
  choice: LineChoice | undefined;
  onChoose: (c: LineChoice) => void;
}) {
  return (
    <div className="rounded-lg border border-accent/25 bg-panel2/50 px-3 py-2.5">
      {/* Original line */}
      <div className="mb-2 flex items-baseline gap-2">
        <span className="shrink-0 rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-[10px]
                         text-zinc-400">
          {entry.quantity}×
        </span>
        <span className="font-mono text-[11px] text-zinc-500 line-through">
          {entry.name}
        </span>
      </div>

      {/* Suggestion chips + Skip */}
      <div className="flex flex-wrap gap-1.5">
        {entry.suggestions.map((sugg) => {
          const selected = choice === sugg.id;
          return (
            <button
              key={sugg.id}
              onClick={() => onChoose(sugg.id)}
              className={[
                "rounded-md border px-2 py-1 text-[11px] font-medium transition",
                selected
                  ? "border-accent/70 bg-accent/20 text-accent"
                  : "border-zinc-700 text-zinc-300 hover:border-accent/40 hover:text-accent",
              ].join(" ")}
            >
              {sugg.name}
            </button>
          );
        })}
        <button
          onClick={() => onChoose("skip")}
          className={[
            "rounded-md border px-2 py-1 text-[11px] font-medium transition",
            choice === "skip"
              ? "border-zinc-500 bg-zinc-700 text-zinc-300"
              : "border-zinc-800 text-zinc-600 hover:border-zinc-600 hover:text-zinc-400",
          ].join(" ")}
        >
          Skip
        </button>
      </div>

      {/* Chosen label */}
      {choice && choice !== "skip" && (
        <p className="mt-1.5 text-[10px] text-accent/70">
          Will import as:{" "}
          <span className="font-semibold text-accent">
            {entry.suggestions.find((s) => s.id === choice)?.name}
          </span>
        </p>
      )}
    </div>
  );
}
