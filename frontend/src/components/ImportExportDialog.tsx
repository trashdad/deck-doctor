"use client";

/**
 * SP6 — paste-a-decklist import dialog. SCAFFOLD — implement per roadmap §6.5.
 *
 * Modal: fixed inset-0 z-[160] backdrop (bg-black/60) + centered panel
 * (max-w-xl w-full bg-panel border border-edge rounded-xl p-4), ESC + backdrop close.
 * Contents:
 * - title "Import decklist", hint line "Moxfield / Archidekt / MTGO / Arena formats".
 * - name <input> (default "Imported deck").
 * - <textarea> h-64 font-mono text-xs (placeholder shows two sample lines).
 * - Import button → api.importDeck(text, name) → on success:
 *     useDecksStore.load(result.deck.id); if result.unresolved.length, keep the dialog
 *     open showing an amber warning list ("N lines didn't resolve:") with the lines;
 *     else close.
 * - Errors (network/4xx) render in red below the button.
 * data-testid: "import-dialog", textarea "import-text", button "import-submit".
 */
export function ImportExportDialog({
  isOpen,
  onClose,
}: {
  isOpen: boolean;
  onClose: () => void;
}) {
  if (!isOpen) return null;
  void onClose;
  // TODO(SP6): implement per the docstring above.
  return null;
}
