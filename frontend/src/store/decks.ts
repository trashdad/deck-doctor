/**
 * SP6 — saved-deck client state.
 *
 * - refresh(): GET /decks -> deckList.
 * - saveCurrent(name?): POST when currentId === null, else PUT. Cards come from the
 *   useDeck store (zone per entry) + basics (id -> quantity).
 * - load(id): GET the deck, repopulate useDeck (clear, add, move, setBasic), set currentId.
 * - remove(id): DELETE; clears currentId if it was the open deck.
 */
import { create } from "zustand";
import type { DeckSummary, DeckEntry } from "@/lib/types";
import type { Zone } from "@/lib/zones";
import {
  listDecks,
  saveDeck,
  updateDeck,
  getDeck,
  deleteDeck,
} from "@/lib/api";
import { useDeck } from "./deck";

interface DecksState {
  deckList: DeckSummary[];
  currentId: string | null;
  currentName: string;
  dirty: boolean;

  refresh: () => Promise<void>;
  saveCurrent: (name?: string) => Promise<void>;
  load: (id: string) => Promise<void>;
  remove: (id: string) => Promise<void>;
  markDirty: () => void;
}

/** Build the DeckEntry[] payload from the live deck store (cards + basics). */
function currentEntries(): { entries: DeckEntry[]; commanderId: string | null } {
  const { cards, basics } = useDeck.getState();
  const entries: DeckEntry[] = Object.values(cards).map((dc) => ({
    id: dc.card.id,
    zone: dc.zone,
    quantity: 1,
  }));
  for (const [id, b] of Object.entries(basics)) {
    entries.push({ id, zone: "Lands", quantity: b.quantity });
  }
  const commanderId =
    Object.values(cards).find((dc) => dc.zone === "Commanders")?.card.id ?? null;
  return { entries, commanderId };
}

export const useDecksStore = create<DecksState>((set, get) => ({
  deckList: [],
  currentId: null,
  currentName: "Untitled",
  dirty: false,

  refresh: async () => {
    const deckList = await listDecks();
    set({ deckList });
  },

  saveCurrent: async (name) => {
    const { entries, commanderId } = currentEntries();
    const finalName = name ?? get().currentName ?? "Untitled";
    const { currentId } = get();
    let saved;
    if (currentId === null) {
      saved = await saveDeck(finalName, commanderId, entries);
    } else {
      saved = await updateDeck(currentId, finalName, commanderId, entries);
    }
    set({ currentId: saved.id, currentName: saved.name, dirty: false });
    await get().refresh();
  },

  load: async (id) => {
    const detail = await getDeck(id);
    const deck = useDeck.getState();
    deck.clear();
    for (const row of detail.cards) {
      if (row.zone === "Lands" && (row.card.type_line || "").includes("Basic")) {
        deck.setBasic(row.card.id, row.quantity, row.card);
        continue;
      }
      deck.add(row.card);
      deck.move(row.card.id, row.zone as Zone);
    }
    set({ currentId: detail.id, currentName: detail.name, dirty: false });
  },

  remove: async (id) => {
    await deleteDeck(id);
    if (get().currentId === id) set({ currentId: null, currentName: "Untitled" });
    await get().refresh();
  },

  markDirty: () => set({ dirty: true }),
}));
