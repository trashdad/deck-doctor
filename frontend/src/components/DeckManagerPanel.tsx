"use client";

/**
 * SP6 — saved-decks panel. SCAFFOLD — implement per roadmap §6.5.
 *
 * Chrome: copy SuggestionsPanel.tsx exactly (backdrop z-[110] + right panel w-[460px]
 * z-[115], ESC closes, header with ✕). Opened from a header button `🗂 Decks` in page.tsx
 * (always enabled) — page.tsx owns `const [decksOpen, setDecksOpen] = useState(false)`.
 *
 * Contents top-to-bottom:
 * 1. "Save as…" row: name <input> (defaults to current deck name or "Untitled") +
 *    gold Save button → useDecksStore.saveCurrent(name) → refresh().
 * 2. Deck list (useDecksStore.deckList, refreshed on open): per row — name (truncate),
 *    `{card_count} cards · {relative updated time}`, click row → load(id) + close panel;
 *    🗑 button → window.confirm(`Delete "${name}"?`) → remove(id).
 *    Highlight the row whose id === currentId (border-accent).
 * 3. Footer buttons: "Import…" → opens ImportExportDialog (page.tsx state);
 *    "Export" (disabled until currentId) → fetch(exportDeckUrl(currentId)).text() →
 *    Blob download named `${name}.txt`.
 * data-testid: "deck-manager-panel", rows "deck-row", save "deck-save".
 */
export function DeckManagerPanel({
  isOpen,
  onClose,
  onOpenImport,
}: {
  isOpen: boolean;
  onClose: () => void;
  onOpenImport: () => void;
}) {
  if (!isOpen) return null;
  void onClose;
  void onOpenImport;
  // TODO(SP6): implement per the docstring above.
  return null;
}
