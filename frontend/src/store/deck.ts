import { create } from "zustand";
import type { Card } from "@/lib/types";
import { autoZone, type Zone } from "@/lib/zones";

/** Union color identity of all commander(s) currently in the deck (empty = none set). */
export function commanderIdentity(cards: Record<string, { card: Card; zone: Zone }>): Set<string> {
  const ci = new Set<string>();
  for (const dc of Object.values(cards)) {
    if (dc.zone === "Commanders") (dc.card.color_identity ?? []).forEach((c) => ci.add(c));
  }
  return ci;
}

/** A card is legal if its color identity is a subset of the commander's. */
export function withinIdentity(ci: Set<string>, card: Card): boolean {
  return (card.color_identity ?? []).every((c) => ci.has(c));
}

export interface DeckCard {
  card: Card;
  zone: Zone;
}

export interface BasicEntry {
  card: Card;
  quantity: number;
}

interface DeckState {
  cards: Record<string, DeckCard>; // keyed by card id (singletons)
  basics: Record<string, BasicEntry>; // basic lands with multiplicity
  add: (card: Card) => void;
  remove: (id: string) => void;
  move: (id: string, zone: Zone) => void;
  setBasic: (id: string, quantity: number, card?: Card) => void;
  /**
   * Set a commander. `asPartner` false (default) replaces any existing
   * commander(s) and prunes the deck to the new color identity; true adds the
   * card alongside as a partner (color identity widens to the union).
   */
  setCommander: (card: Card, asPartner?: boolean) => void;
  clear: () => void;
  /**
   * Bulk-load an imported decklist directly into the store.
   *
   * Bypasses the color-identity gate — import is authoritative. Basic lands
   * (type_line includes "Basic") go to `basics` with their quantity; everything
   * else goes to `cards` at its given zone (singleton). If `replace` is true
   * (default), the store is cleared first.
   */
  loadImported: (
    rows: { card: Card; zone: Zone; quantity: number }[],
    replace?: boolean,
  ) => void;
}

export const useDeck = create<DeckState>((set) => ({
  cards: {},
  basics: {},
  add: (card) =>
    set((s) => {
      if (s.cards[card.id]) return s;
      const zone = autoZone(card);

      // Color-identity GATE: once a commander is set, an off-color non-commander
      // card can't be added at all.
      if (zone !== "Commanders") {
        const ci = commanderIdentity(s.cards);
        if (ci.size > 0 && !withinIdentity(ci, card)) return s;
      }

      const cards = { ...s.cards, [card.id]: { card, zone } };

      // Selecting a commander enforces color identity on the EXISTING deck: any
      // card/basic whose identity isn't a subset of the commander(s)' is dropped.
      // (Union of all Commanders-zone cards handles partner pairs.)
      if (zone === "Commanders") {
        const ci = commanderIdentity(cards);
        const prunedCards = Object.fromEntries(
          Object.entries(cards).filter(([, dc]) => dc.zone === "Commanders" || withinIdentity(ci, dc.card)),
        );
        const prunedBasics = Object.fromEntries(
          Object.entries(s.basics).filter(([, be]) => withinIdentity(ci, be.card)),
        );
        return { cards: prunedCards, basics: prunedBasics };
      }
      return { cards };
    }),
  remove: (id) =>
    set((s) => {
      const next = { ...s.cards };
      delete next[id];
      return { cards: next };
    }),
  move: (id, zone) =>
    set((s) => {
      const dc = s.cards[id];
      if (!dc) return s;
      return { cards: { ...s.cards, [id]: { ...dc, zone } } };
    }),
  setBasic: (id, quantity, card) =>
    set((s) => {
      const next = { ...s.basics };
      if (quantity <= 0) {
        delete next[id];
      } else {
        const existing = next[id];
        const c = card ?? existing?.card;
        if (!c) return s; // need a Card to render the first time
        next[id] = { card: c, quantity };
      }
      return { basics: next };
    }),
  setCommander: (card, asPartner = false) =>
    set((s) => {
      const cards: Record<string, DeckCard> = { ...s.cards };
      if (!asPartner) {
        // Replacing the commander: drop any existing commander(s) first.
        for (const [id, dc] of Object.entries(cards)) {
          if (dc.zone === "Commanders") delete cards[id];
        }
      }
      cards[card.id] = { card, zone: "Commanders" };
      // Re-enforce color identity against the (possibly new/union) commander set.
      const ci = commanderIdentity(cards);
      const prunedCards = Object.fromEntries(
        Object.entries(cards).filter(([, dc]) => dc.zone === "Commanders" || withinIdentity(ci, dc.card)),
      );
      const prunedBasics = Object.fromEntries(
        Object.entries(s.basics).filter(([, be]) => withinIdentity(ci, be.card)),
      );
      return { cards: prunedCards, basics: prunedBasics };
    }),
  clear: () => set({ cards: {}, basics: {} }),
  loadImported: (rows, replace = true) =>
    set((s) => {
      const nextCards: Record<string, DeckCard> = replace ? {} : { ...s.cards };
      const nextBasics: Record<string, BasicEntry> = replace ? {} : { ...s.basics };

      for (const { card, zone, quantity } of rows) {
        if ((card.type_line ?? "").includes("Basic")) {
          // Basic land — track with multiplicity
          const existing = nextBasics[card.id];
          nextBasics[card.id] = {
            card,
            quantity: existing ? existing.quantity + quantity : quantity,
          };
        } else {
          // Non-basic — singleton; zone comes from the imported row
          nextCards[card.id] = { card, zone };
        }
      }

      return { cards: nextCards, basics: nextBasics };
    }),
}));
