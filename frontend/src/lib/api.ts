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

export function getCommanders(): Promise<Card[]> {
  return get<Card[]>("/cards/commanders");
}

export function searchByOracleText(
  pattern: string,
  limit = 50,
): Promise<Card[]> {
  const qs = new URLSearchParams({ pattern, limit: String(limit) });
  return get<Card[]>(`/cards/oracle?${qs.toString()}`);
}

export interface CardSemantics {
  flat_tags: string[];
  ability_tags: string[][];
}

export function getCardSemantics(cardId: string): Promise<CardSemantics> {
  return get<CardSemantics>(`/cards/${cardId}/semantics`);
}

export function searchBySemantics(params: {
  linkedTags?: string[];
  flatTags?: string[];
  limit?: number;
}): Promise<Card[]> {
  const qs = new URLSearchParams();
  if (params.linkedTags?.length) qs.set("linked_tags", params.linkedTags.join(","));
  if (params.flatTags?.length) qs.set("flat_tags", params.flatTags.join(","));
  if (params.limit != null) qs.set("limit", String(params.limit));
  return get<Card[]>(`/cards/by-semantics?${qs.toString()}`);
}

export function getSimilarCards(cardId: string, limit = 20): Promise<Card[]> {
  return get<Card[]>(`/cards/${cardId}/similar?limit=${limit}`);
}

export function getComboCards(cardId: string, limit = 20): Promise<Card[]> {
  return get<Card[]>(`/cards/${cardId}/combos?limit=${limit}`);
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
