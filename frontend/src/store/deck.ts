import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Card } from "@/lib/types";
import { type Zone } from "@/lib/zones";
import { matchingZones } from "@/lib/functions";

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

/** Shallow copy of the mutable deck state, for the undo ring. */
export interface Snapshot {
  cards: Record<string, DeckCard>;
  basics: Record<string, BasicEntry>;
}

/** Undo ring depth (plan §7.3). */
export const MAX_HISTORY = 20;

export interface DeckState {
  cards: Record<string, DeckCard>; // keyed by card id (singletons)
  basics: Record<string, BasicEntry>; // basic lands with multiplicity
  /** Undo ring — every mutating action pushes the pre-change snapshot. Not persisted. */
  history: Snapshot[];
  future: Snapshot[];
  undo: () => boolean;
  redo: () => boolean;
  add: (card: Card) => void;
  remove: (id: string) => void;
  move: (id: string, zone: Zone) => void;
  /**
   * Replace `oldId` with `newCard`, dropping it into the SAME zone the replaced
   * card occupied (an upgrade keeps its place in the board). No-op if the
   * replacement is already in the deck.
   */
  swap: (oldId: string, newCard: Card) => void;
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

/** Apply `patch` and push the pre-change snapshot onto the undo ring (clears redo). */
function withHistory(s: DeckState, patch: Partial<Snapshot>): Partial<DeckState> {
  const snap: Snapshot = { cards: s.cards, basics: s.basics };
  return {
    ...patch,
    history: [...s.history.slice(-(MAX_HISTORY - 1)), snap],
    future: [],
  };
}

export const useDeck = create<DeckState>()(
  persist(
    (set, get) => ({
  cards: {},
  basics: {},
  history: [],
  future: [],
  undo: () => {
    const s = get();
    const prev = s.history[s.history.length - 1];
    if (!prev) return false;
    set({
      cards: prev.cards,
      basics: prev.basics,
      history: s.history.slice(0, -1),
      future: [...s.future.slice(-(MAX_HISTORY - 1)), { cards: s.cards, basics: s.basics }],
    });
    return true;
  },
  redo: () => {
    const s = get();
    const next = s.future[s.future.length - 1];
    if (!next) return false;
    set({
      cards: next.cards,
      basics: next.basics,
      future: s.future.slice(0, -1),
      history: [...s.history.slice(-(MAX_HISTORY - 1)), { cards: s.cards, basics: s.basics }],
    });
    return true;
  },
  add: (card) =>
    set((s) => {
      if (s.cards[card.id]) return s;
      // Adding from search NEVER sets the commander (that's setCommander's job via
      // the Commanders tab). Legendary creatures land in their function zone, not
      // the Commander zone — so a second legendary creature goes to Ramp/Utility/etc.
      // Detected win conditions drop into the dedicated Win Conditions strip;
      // everything else flows to its function zone.
      const zone = card.wincon ? "Win Conditions" : matchingZones(card)[0];

      // Color-identity gate: once a commander is set, off-color cards can't be added.
      const ci = commanderIdentity(s.cards);
      if (ci.size > 0 && !withinIdentity(ci, card)) return s;

      return withHistory(s, { cards: { ...s.cards, [card.id]: { card, zone } } });
    }),
  remove: (id) =>
    set((s) => {
      if (!s.cards[id]) return s;
      const next = { ...s.cards };
      delete next[id];
      return withHistory(s, { cards: next });
    }),
  move: (id, zone) =>
    set((s) => {
      const dc = s.cards[id];
      if (!dc || dc.zone === zone) return s;
      return withHistory(s, { cards: { ...s.cards, [id]: { ...dc, zone } } });
    }),
  swap: (oldId, newCard) =>
    set((s) => {
      if (s.cards[newCard.id]) return s; // replacement already present
      const old = s.cards[oldId];
      const zone: Zone = old
        ? old.zone
        : newCard.wincon
          ? "Win Conditions"
          : matchingZones(newCard)[0];
      const next = { ...s.cards };
      delete next[oldId];
      next[newCard.id] = { card: newCard, zone };
      return withHistory(s, { cards: next });
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
      return withHistory(s, { basics: next });
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
      return withHistory(s, { cards: prunedCards, basics: prunedBasics });
    }),
  clear: () => set((s) => withHistory(s, { cards: {}, basics: {} })),
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

      return withHistory(s, { cards: nextCards, basics: nextBasics });
    }),
    }),
    {
      // Persist the working deck (cards + basics, including the Card objects) so it
      // survives a reload / browser Back — no progress lost. Methods and the undo
      // ring aren't stored.
      name: "simmander.deck",
      partialize: (s) => ({ cards: s.cards, basics: s.basics }),
    },
  ),
);
