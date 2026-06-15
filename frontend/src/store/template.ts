import { create } from "zustand";
import type { TemplateInfo, ThemeInfo } from "@/lib/types";

const COMPOSITE_ID = "simmander_composite";

// Mirrors backend templates.py simmander_composite — correct before the catalog loads.
const DEFAULT_COMPOSITE_COUNTS: Record<string, number> = {
  land: 37,
  ramp: 10,
  card_draw: 9,
  removal: 8,
  board_wipe: 3,
};

export interface CompositeState {
  counts: Record<string, number>;
  themeA: string; // theme id, or "" for none
  themeB: string;
  themeC: string;
  freeText: string;
}

interface TemplateStore {
  templates: TemplateInfo[];
  themes: ThemeInfo[];
  loaded: boolean;
  selectedId: string;
  composite: CompositeState;
  panelOpen: boolean;

  setCatalog: (templates: TemplateInfo[], themes: ThemeInfo[]) => void;
  select: (id: string) => void;
  setCount: (cat: string, n: number) => void;
  setThemeA: (id: string) => void;
  setThemeB: (id: string) => void;
  setThemeC: (id: string) => void;
  setFreeText: (text: string) => void;
  openPanel: () => void;
  closePanel: () => void;
  /** Counts the Deck Doctor should fill toward for the active selection. */
  activeCounts: () => Record<string, number>;
}

export const COMPOSITE_TEMPLATE_ID = COMPOSITE_ID;

export const useTemplateStore = create<TemplateStore>((set, get) => ({
  templates: [],
  themes: [],
  loaded: false,
  selectedId: COMPOSITE_ID,
  composite: {
    counts: { ...DEFAULT_COMPOSITE_COUNTS },
    themeA: "",
    themeB: "",
    themeC: "",
    freeText: "",
  },
  panelOpen: false,

  setCatalog: (templates, themes) =>
    set((s) => {
      // Seed the composite's editable counts from the server's composite preset
      // the first time the catalog arrives (unless the user has already edited).
      const preset = templates.find((t) => t.id === COMPOSITE_ID);
      const composite =
        s.loaded || !preset
          ? s.composite
          : { ...s.composite, counts: { ...preset.counts } };
      return { templates, themes, loaded: true, composite };
    }),

  select: (id) =>
    set(() => ({
      selectedId: id,
      panelOpen: id === COMPOSITE_ID,
    })),

  setCount: (cat, n) =>
    set((s) => ({
      composite: {
        ...s.composite,
        counts: { ...s.composite.counts, [cat]: Math.max(0, Math.round(n)) },
      },
    })),

  setThemeA: (id) => set((s) => ({ composite: { ...s.composite, themeA: id } })),
  setThemeB: (id) => set((s) => ({ composite: { ...s.composite, themeB: id } })),
  setThemeC: (id) => set((s) => ({ composite: { ...s.composite, themeC: id } })),
  setFreeText: (text) =>
    set((s) => ({ composite: { ...s.composite, freeText: text } })),

  openPanel: () => set({ panelOpen: true }),
  closePanel: () => set({ panelOpen: false }),

  activeCounts: () => {
    const { selectedId, templates, composite } = get();
    if (selectedId === COMPOSITE_ID) return composite.counts;
    return templates.find((t) => t.id === selectedId)?.counts ?? composite.counts;
  },
}));
