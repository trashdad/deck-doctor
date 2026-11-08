import type { Reason } from "@/lib/types";
import type { CardContext } from "@/store/ui";
import { formatSignal } from "@/lib/formatSignal";

/*
 * Sentence templates for plan §5.1. Pure. Templates only re-phrase what the
 * backend's `detail` string already says; any number is parsed from `detail`
 * or taken from `value` at the precision the backend returned. Unknown
 * signals fall back to `detail` verbatim — never hidden, never invented.
 */

export interface SourceInfo {
  label: string;
  /** false → the backend sent a signal this UI has no product name for. */
  known: boolean;
}

/**
 * Product names for the backend's signal ids. Unknown ids are labelled OTHER in
 * the row (raw ids never show in product copy); the evidence list names them.
 */
export function sourceInfo(signal: string): SourceInfo {
  switch (signal) {
    case "edhrec":
    case "edhrec_inclusion":
      return { label: "EDHREC", known: true };
    case "cooccurrence":
      return { label: "REAL DECKS", known: true };
    case "synergy":
      return { label: "MECHANICS", known: true };
    case "engine":
      return { label: "COMBO", known: true };
    case "staple":
      return { label: "STAPLE", known: true };
    default:
      return { label: "OTHER", known: false };
  }
}

/* Numbers live in chips, not in sentence copy (§3.5): a trailing "(… -0.15)" style
   parenthetical from the backend is dropped from the sentence — the evidence list
   still shows the raw detail. */
const stripParenNumbers = (s: string) => s.replace(/\s*\([^()]*-?\d[^()]*\)\s*$/, "").trim();

const pctIn = (detail: string): string | null => {
  const m = detail.match(/(\d+(?:\.\d+)?)\s?%/);
  return m ? `${m[1]} %` : null;
};
const countOfYours = (detail: string): string | null => {
  const m = detail.match(/(\d+)\s+of your/);
  return m ? m[1] : null;
};

export function reasonSentence(r: Reason, commanderName: string | null, context: CardContext = "suggest"): string {
  const cmd = commanderName ?? "this commander";
  const detail = (r.detail ?? "").trim();
  // Cuts: "EDHREC: in 50% of this commander's decks (synergy -0.15)" → the inclusion
  // sentence; the synergy number stays in the chip / evidence list.
  if (context === "cut" && r.signal === "edhrec") {
    const pct = pctIn(detail);
    if (pct) return `In ${pct} of ${cmd}'s EDHREC decks.`;
    return stripParenNumbers(detail) || `EDHREC signal for ${cmd}.`;
  }

  switch (r.signal) {
    case "edhrec":
      return `Signature card for ${cmd} on EDHREC.`;
    case "edhrec_inclusion": {
      const pct = pctIn(detail);
      return pct ? `In ${pct} of ${cmd}'s EDHREC decks.` : detail;
    }
    case "cooccurrence": {
      const n = countOfYours(detail);
      return n ? `Real decks run it with ${n} of your cards.` : "Real decks run it with your cards.";
    }
    case "synergy": {
      const n = countOfYours(detail);
      return n ? `Its mechanics fit ${n} of your cards.` : "Its mechanics fit cards you already run.";
    }
    case "engine": {
      // "completes combo → Infinite mana: A + B" | "completes combo: A + B" | "completes X engine: A + B"
      const m = detail.match(/^completes\s+([^:]*?)(?:\s*→\s*([^:]+))?:\s*(.+)$/i);
      if (m) {
        const members = m[3].trim();
        const produces = m[2]?.trim();
        return `Completes a combo you are one card from: ${members}${produces ? ` → ${produces}` : ""}.`;
      }
      return detail;
    }
    case "staple":
      return "Format staple in your colors — not deck-specific.";
    default:
      return stripParenNumbers(detail);
  }
}

/** Value for chips / evidence rows: ≤2 decimals, float noise removed (lib/formatSignal). */
export function reasonValue(r: Reason): string {
  return formatSignal(r.value);
}

/**
 * The reason that makes the sentence: highest value first, except that a
 * staple only leads when it is the only signal (staples sit below every
 * deck-specific signal in the product).
 */
export function rankReasons(reasons: Reason[]): Reason[] {
  return [...reasons].sort((a, b) => {
    const sa = a.signal === "staple" ? 1 : 0;
    const sb = b.signal === "staple" ? 1 : 0;
    if (sa !== sb) return sa - sb;
    return (b.value ?? 0) - (a.value ?? 0);
  });
}
