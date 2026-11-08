/**
 * Commander pivot finder — POST /deck/pivot (backend/app/pivot.py).
 *
 * Given the working deck, rank alternative commanders whose EDHREC page the
 * deck's cards match better than the current commander's. Every number comes
 * from data the backend already holds (edhrec_metrics, cards.json, corpus
 * deck counts); a commander without an EDHREC page is omitted, never guessed.
 *
 * Kept in its own module (not api.ts) so the feature can land without touching
 * the shared client; BASE mirrors api.ts (path-hosted at /deck-doctor).
 */
import type { Card, DeckEntry } from "./types";

const BASE_PATH =
  process.env.NEXT_PUBLIC_BASE_PATH === ""
    ? ""
    : process.env.NEXT_PUBLIC_BASE_PATH || "/deck-doctor";
const BASE = `${BASE_PATH}/api`;

export type PivotSignal =
  | "coverage"
  | "edhrec_inclusion"
  | "edhrec_synergy"
  | "off_color"
  | "popularity";

export interface PivotEvidence {
  signal: PivotSignal;
  value: number;
  detail: string;
}

export interface PivotMetrics {
  /** Deck cards that appear on the commander's EDHREC page. */
  hits: number;
  /** Cards listed on that EDHREC page (upper bound on hits). */
  page_size: number;
  /** hits / deck_size */
  coverage: number;
  /** Mean EDHREC inclusion over the whole deck (misses count as 0). */
  inclusion_mean: number;
  /** Mean EDHREC synergy over the hits; null when there are none. */
  synergy_mean: number | null;
  off_color_count: number;
  score: number;
}

export interface PivotCandidate {
  commander: Card;
  /** True when every scored deck card fits the commander's colour identity. */
  in_identity: boolean;
  /** Up to 8 names that would have to be cut (outside its identity). */
  off_color_names: string[];
  /** Corpus decks led by this commander (0 = unknown / none). */
  deck_count: number;
  /** null when the current commander has no EDHREC page to compare against. */
  better_than_current: boolean | null;
  metrics: PivotMetrics;
  /** One human sentence built only from the evidence rows. */
  reason: string;
  evidence: PivotEvidence[];
}

export interface PivotCurrent {
  commander: Card;
  /** null when the current commander has no EDHREC page. */
  metrics: PivotMetrics | null;
}

export interface PivotResponse {
  /** Distinct, resolvable, non-basic deck cards that were scored. */
  deck_size: number;
  /** Union colour identity of those cards, WUBRG order. */
  deck_identity: string[];
  current: PivotCurrent | null;
  candidates: PivotCandidate[];
}

export interface PivotOptions {
  /** Max candidates returned (default 10, server cap 50). */
  limit?: number;
  /** Skip commanders that would force more than this many cuts (default 8). */
  maxOffColor?: number;
  /** Also return candidates that score no better than the current commander. */
  includeAll?: boolean;
}

/** Rank alternative commanders the deck would fit better. */
export async function findCommanderPivots(
  cards: DeckEntry[],
  commander_id: string | null,
  opts: PivotOptions = {},
): Promise<PivotResponse> {
  const qs = new URLSearchParams();
  if (opts.limit != null) qs.set("limit", String(opts.limit));
  if (opts.maxOffColor != null) qs.set("max_off_color", String(opts.maxOffColor));
  if (opts.includeAll) qs.set("include_all", "true");
  const query = qs.toString();
  const res = await fetch(`${BASE}/deck/pivot${query ? `?${query}` : ""}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cards, commander_id }),
    credentials: "include",
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<PivotResponse>;
}
