"use client";

import { useCallback, useEffect, useMemo } from "react";
import type { Card } from "@/lib/types";
import type { Zone } from "@/lib/zones";
import { matchingZones } from "@/lib/functions";
import { useDeck } from "@/store/deck";
import { toast } from "@/components/feedback/toastStore";

/** The lane `useDeck.add` will put the card in (mirrors the store's rule). */
export function landingZone(card: Card): Zone {
  return card.wincon ? "Win Conditions" : matchingZones(card)[0];
}

function deckCount(): number {
  const s = useDeck.getState();
  return (
    Object.keys(s.cards).length +
    Object.values(s.basics).reduce((n, b) => n + b.quantity, 0)
  );
}

/**
 * `useDeck` actions wrapped with the undo ring + an "… · Undo" toast (§4.4).
 * A no-op action (card already present, off-color) shows no toast.
 */
export function useUndoableDeck() {
  const deck = useDeck();

  const undo = useCallback(() => useDeck.getState().undo(), []);
  const redo = useCallback(() => useDeck.getState().redo(), []);

  const add = useCallback((card: Card) => {
    const before = deckCount();
    useDeck.getState().add(card);
    if (deckCount() === before) return false;
    toast({
      message: `Added ${card.name} to ${landingZone(card)}`,
      action: { label: "Undo", onClick: () => useDeck.getState().undo() },
    });
    return true;
  }, []);

  const remove = useCallback((card: Card) => {
    const before = deckCount();
    useDeck.getState().remove(card.id);
    if (deckCount() === before) return false;
    toast({
      message: `Removed ${card.name}`,
      action: { label: "Undo", onClick: () => useDeck.getState().undo() },
    });
    return true;
  }, []);

  const move = useCallback((card: Card, zone: Zone) => {
    const prev = useDeck.getState().cards[card.id]?.zone;
    useDeck.getState().move(card.id, zone);
    if (prev === undefined || prev === zone) return false;
    toast({
      message: `Moved ${card.name} to ${zone}`,
      action: { label: "Undo", onClick: () => useDeck.getState().undo() },
    });
    return true;
  }, []);

  const swap = useCallback((oldCard: Card, newCard: Card) => {
    const had = Boolean(useDeck.getState().cards[newCard.id]);
    useDeck.getState().swap(oldCard.id, newCard);
    if (had) return false;
    toast({
      message: `Swapped ${oldCard.name} for ${newCard.name}`,
      action: { label: "Undo", onClick: () => useDeck.getState().undo() },
    });
    return true;
  }, []);

  const setCommander = useCallback((card: Card, asPartner = false) => {
    const before = deckCount();
    useDeck.getState().setCommander(card, asPartner);
    const pruned = Math.max(0, before + 1 - deckCount());
    toast({
      message: pruned > 0
        ? `${card.name} is now the commander · ${pruned} off-color card${pruned === 1 ? "" : "s"} removed`
        : `${card.name} is now the commander`,
      action: { label: "Undo", onClick: () => useDeck.getState().undo() },
    });
    return true;
  }, []);

  return useMemo(
    () => ({ add, remove, move, swap, setCommander, undo, redo, canUndo: deck.history.length > 0, canRedo: deck.future.length > 0 }),
    [add, remove, move, swap, setCommander, undo, redo, deck.history.length, deck.future.length],
  );
}

/** Global Ctrl/⌘+Z → undo, Ctrl/⌘+Shift+Z (or Ctrl+Y) → redo. Mount once per page. */
export function useUndoHotkeys(enabled = true) {
  useEffect(() => {
    if (!enabled) return;
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      const mod = e.ctrlKey || e.metaKey;
      if (!mod) return;
      if (e.key.toLowerCase() === "z" && !e.shiftKey) {
        if (useDeck.getState().undo()) e.preventDefault();
      } else if ((e.key.toLowerCase() === "z" && e.shiftKey) || e.key.toLowerCase() === "y") {
        if (useDeck.getState().redo()) e.preventDefault();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enabled]);
}
