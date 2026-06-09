"use client";

import { create } from "zustand";
import type { Card } from "@/lib/types";
import type { PhraseVariant } from "@/lib/oracle";

interface OracleState {
  // Hover detail
  hoveredCard: Card | null;
  hoverAnchor: { x: number; y: number; side: "left" | "right" } | null;

  // Phrase panel (right drawer)
  phraseVariants: PhraseVariant[] | null;
  selectedPattern: string | null;

  setHover: (
    card: Card | null,
    anchor?: { x: number; y: number; side: "left" | "right" },
  ) => void;
  openPhrase: (variants: PhraseVariant[], initialPattern?: string) => void;
  selectPattern: (pattern: string) => void;
  closePhrase: () => void;
}

export const useOracle = create<OracleState>((set) => ({
  hoveredCard: null,
  hoverAnchor: null,
  phraseVariants: null,
  selectedPattern: null,

  setHover: (card, anchor) =>
    set({ hoveredCard: card, hoverAnchor: anchor ?? null }),

  openPhrase: (variants, initialPattern) =>
    set({ phraseVariants: variants, selectedPattern: initialPattern ?? variants[0]?.pattern ?? null }),

  selectPattern: (pattern) => set({ selectedPattern: pattern }),

  closePhrase: () => set({ phraseVariants: null, selectedPattern: null }),
}));
