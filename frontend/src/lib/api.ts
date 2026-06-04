import type { Card, DeckAnalysis, DeckEntry, SynergyEdge } from "./types";

// Calls go through Next's /api rewrite -> FastAPI (see next.config.mjs).
const BASE = "/api";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export function searchCards(params: {
  q?: string;
  colors?: string;
  type?: string;
  max_cmc?: number;
}): Promise<Card[]> {
  const qs = new URLSearchParams();
  if (params.q) qs.set("q", params.q);
  if (params.colors) qs.set("colors", params.colors);
  if (params.type) qs.set("type", params.type);
  if (params.max_cmc != null) qs.set("max_cmc", String(params.max_cmc));
  return get<Card[]>(`/cards?${qs.toString()}`);
}

export function analyzeDeck(
  cards: DeckEntry[],
  commander_id: string | null,
): Promise<DeckAnalysis> {
  return post<DeckAnalysis>("/deck/analyze", { cards, commander_id });
}

export function recommend(
  cards: DeckEntry[],
  commander_id: string | null,
): Promise<SynergyEdge[]> {
  return post<SynergyEdge[]>("/deck/recommend", { cards, commander_id });
}
