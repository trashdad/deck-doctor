import type {
  Card,
  CompleteResponse,
  CutsResponse,
  DeckCombos,
  DeckDetail,
  DeckEntry,
  DeckSummary,
  DeckAnalysis,
  EngineGroup,
  GraphResponse,
  ImportResult,
  PairScoreFull,
  RelationshipAxis,
  RelationshipNeighbor,
  SpellbookCombo,
  SuggestionResponse,
} from "./types";

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

export function recommendCards(
  cards: DeckEntry[],
  commander_id: string,
  opts: { limit?: number; explain?: boolean } = {},
): Promise<SuggestionResponse> {
  const qs = new URLSearchParams();
  if (opts.limit != null) qs.set("limit", String(opts.limit));
  if (opts.explain) qs.set("explain", "true");
  return post<SuggestionResponse>(`/deck/recommend?${qs.toString()}`, {
    cards,
    commander_id,
  });
}

export function getRelationships(
  cardId: string,
  axis: RelationshipAxis,
  limit = 30,
): Promise<RelationshipNeighbor[]> {
  return get<RelationshipNeighbor[]>(
    `/cards/${cardId}/relationships?axis=${axis}&limit=${limit}`,
  );
}

export function getCombosEngines(cardId: string): Promise<EngineGroup[]> {
  return get<EngineGroup[]>(`/cards/${cardId}/combos-engines`);
}

export function getPairScore(a: string, b: string): Promise<PairScoreFull> {
  return get<PairScoreFull>(
    `/score/pair?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`,
  );
}

export function getCard(cardId: string): Promise<Card> {
  return get<Card>(`/cards/${cardId}`);
}

// ---- SP6: deck persistence ----
async function del(path: string): Promise<void> {
  const res = await fetch(`${BASE}${path}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
}

async function put<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export function listDecks(): Promise<DeckSummary[]> {
  return get<DeckSummary[]>("/decks");
}

export function saveDeck(
  name: string,
  commander_id: string | null,
  cards: DeckEntry[],
): Promise<DeckDetail> {
  return post<DeckDetail>("/decks", { name, commander_id, cards });
}

export function updateDeck(
  deckId: string,
  name: string,
  commander_id: string | null,
  cards: DeckEntry[],
): Promise<DeckDetail> {
  return put<DeckDetail>(`/decks/${deckId}`, { name, commander_id, cards });
}

export function getDeck(deckId: string): Promise<DeckDetail> {
  return get<DeckDetail>(`/decks/${deckId}`);
}

export function deleteDeck(deckId: string): Promise<void> {
  return del(`/decks/${deckId}`);
}

export function importDeck(text: string, name?: string): Promise<ImportResult> {
  return post<ImportResult>("/decks/import", { text, name: name ?? "Imported deck" });
}

/** Direct URL for the text export (use in an <a download> or fetch().text()). */
export function exportDeckUrl(deckId: string): string {
  return `${BASE}/decks/${deckId}/export`;
}

// ---- SP7: Commander Spellbook ----
export function postDeckCombos(
  cards: DeckEntry[],
  commander_id: string | null,
): Promise<DeckCombos> {
  return post<DeckCombos>("/deck/combos", { cards, commander_id });
}

export function getSpellbookCombos(
  cardId: string,
  limit = 20,
): Promise<SpellbookCombo[]> {
  return get<SpellbookCombo[]>(`/cards/${cardId}/spellbook-combos?limit=${limit}`);
}

// ---- SP8: deck doctor ----
export function postDeckComplete(
  cards: DeckEntry[],
  commander_id: string,
): Promise<CompleteResponse> {
  return post<CompleteResponse>("/deck/complete", { cards, commander_id });
}

export function postDeckCuts(
  cards: DeckEntry[],
  commander_id: string,
  limit = 10,
): Promise<CutsResponse> {
  return post<CutsResponse>(`/deck/cuts?limit=${limit}`, { cards, commander_id });
}

// ---- SP9: synergy graph ----
export function postDeckGraph(
  cards: DeckEntry[],
  commander_id: string | null,
): Promise<GraphResponse> {
  return post<GraphResponse>("/deck/graph", { cards, commander_id });
}
