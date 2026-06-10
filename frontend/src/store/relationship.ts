import { create } from "zustand";
import type {
  Card,
  EngineGroup,
  PairScoreFull,
  RelationshipNeighbor,
  SpellbookCombo,
} from "@/lib/types";
import {
  getCombosEngines,
  getPairScore,
  getRelationships,
  getSimilarCards,
  getSpellbookCombos,
} from "@/lib/api";

// The explorer's five tabs: three typed SP1/SP3 axes, the engines view, and the
// legacy semantic-tag similarity (kept as a distinct, clearly-labeled notion).
export type ExplorerAxis = "similar" | "synergy" | "cooccurrence" | "combos" | "tags";

interface AxisData {
  neighbors?: RelationshipNeighbor[];
  engines?: EngineGroup[];
  spellbook?: SpellbookCombo[];
  tagSimilar?: Card[];
}

interface RelationshipState {
  isOpen: boolean;
  focal: Card | null;
  axis: ExplorerAxis;
  stack: Card[]; // pivot breadcrumb (previous focal cards)
  data: AxisData | null;
  inspect: { card: Card; pair: PairScoreFull | null; loading: boolean } | null;
  loading: boolean;

  open: (card: Card, axis?: ExplorerAxis) => void;
  setAxis: (axis: ExplorerAxis) => void;
  pivot: (card: Card) => void;
  back: () => void;
  inspectCard: (card: Card) => void;
  closeInspect: () => void;
  close: () => void;
}

const cache = new Map<string, AxisData>();

async function fetchAxis(card: Card, axis: ExplorerAxis): Promise<AxisData> {
  const key = `${card.id}:${axis}`;
  const hit = cache.get(key);
  if (hit) return hit;
  let data: AxisData;
  if (axis === "combos") {
    const [engines, spellbook] = await Promise.all([
      getCombosEngines(card.id),
      getSpellbookCombos(card.id, 20),
    ]);
    data = { engines, spellbook };
  } else if (axis === "tags") {
    data = { tagSimilar: await getSimilarCards(card.id, 30) };
  } else {
    data = { neighbors: await getRelationships(card.id, axis, 30) };
  }
  cache.set(key, data);
  return data;
}

export const useRelationshipStore = create<RelationshipState>((set, get) => {
  async function load(card: Card, axis: ExplorerAxis) {
    set({ loading: true, data: null, inspect: null });
    try {
      const data = await fetchAxis(card, axis);
      // Drop stale responses after a rapid pivot/tab switch.
      const s = get();
      if (s.focal?.id === card.id && s.axis === axis) {
        set({ data, loading: false });
      }
    } catch {
      set({ data: {}, loading: false });
    }
  }

  return {
    isOpen: false,
    focal: null,
    axis: "synergy",
    stack: [],
    data: null,
    inspect: null,
    loading: false,

    open: (card, axis = "synergy") => {
      set({ isOpen: true, focal: card, axis, stack: [] });
      void load(card, axis);
    },

    setAxis: (axis) => {
      const { focal } = get();
      if (!focal) return;
      set({ axis });
      void load(focal, axis);
    },

    pivot: (card) => {
      const { focal, axis, stack } = get();
      if (!focal || card.id === focal.id) return;
      set({ focal: card, stack: [...stack, focal] });
      void load(card, axis);
    },

    back: () => {
      const { stack, axis } = get();
      if (stack.length === 0) return;
      const prev = stack[stack.length - 1];
      set({ focal: prev, stack: stack.slice(0, -1) });
      void load(prev, axis);
    },

    inspectCard: (card) => {
      const { focal } = get();
      if (!focal) return;
      set({ inspect: { card, pair: null, loading: true } });
      getPairScore(focal.id, card.id)
        .then((pair) => {
          const cur = get().inspect;
          if (cur?.card.id === card.id) {
            set({ inspect: { card, pair, loading: false } });
          }
        })
        .catch(() => {
          const cur = get().inspect;
          if (cur?.card.id === card.id) {
            set({ inspect: { card, pair: null, loading: false } });
          }
        });
    },

    closeInspect: () => set({ inspect: null }),

    close: () =>
      set({ isOpen: false, focal: null, stack: [], data: null, inspect: null }),
  };
});
