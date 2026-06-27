import { useQuery } from "@tanstack/react-query";
import type {
  Card,
  CommanderSort,
  CompleteResponse,
  CutsResponse,
  DeckCombos,
  DeckDetail,
  DeckDiagnosis,
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
  TemplatesResponse,
  ThemeSuggestResponse,
  UpgradeResponse,
  UpgradeSweepResponse,
} from "./types";
import type { User } from "./types";

// Deck Doctor is path-hosted (simmander.app/deck-doctor), so API calls must carry
// the same prefix: a raw fetch() is NOT basePath-aware. In dev this matches Next's
// rewrite (auto-prefixed to {BASE_PATH}/api → :8001); in prod nginx routes
// {BASE_PATH}/api/ straight to the FastAPI backend. Keep BASE_PATH in sync with
// next.config.mjs. Override with NEXT_PUBLIC_BASE_PATH="" for root hosting.
const BASE_PATH =
  process.env.NEXT_PUBLIC_BASE_PATH === ""
    ? ""
    : process.env.NEXT_PUBLIC_BASE_PATH || "/deck-doctor";
const BASE = `${BASE_PATH}/api`;

const TRACKER_API = "/api"; // simmander.app root — the tracker's shared auth

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { credentials: "include" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    credentials: "include",
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

/** Current user from the shared session, or null. (Deck Doctor's own API.) */
export async function authMe(): Promise<User | null> {
  const res = await fetch(`${BASE}/auth/me`, { credentials: "include" });
  if (!res.ok) return null;
  const data = (await res.json()) as {
    user: { id: number; is_admin?: boolean } | null;
  };
  if (!data.user) return null;
  const isAdmin = !!data.user.is_admin;
  return { id: data.user.id, username: "", is_admin: isAdmin, tier: isAdmin ? "mythic" : "free" };
}

/** Log in via the tracker's shared endpoint (form-encoded). Sets the shared cookie. */
export async function trackerLogin(username: string, password: string): Promise<User> {
  const body = new URLSearchParams({ username, password });
  const res = await fetch(`${TRACKER_API}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
    credentials: "include",
  });
  if (!res.ok) throw new Error("Invalid username or password");
  const data = (await res.json()) as { user: { id: number; username: string } };
  return { id: data.user.id, username: data.user.username };
}

export async function trackerLogout(): Promise<void> {
  await fetch(`${TRACKER_API}/auth/logout`, { method: "POST", credentials: "include" }).catch(
    () => {},
  );
}

export function searchCards(params: {
  q?: string;
  colors?: string;
  type?: string;
  oracle?: string;
  max_cmc?: number;
  commander_id?: string | null;
}): Promise<Card[]> {
  const qs = new URLSearchParams();
  if (params.q) qs.set("q", params.q);
  if (params.oracle) qs.set("oracle", params.oracle);
  if (params.colors) qs.set("colors", params.colors);
  if (params.type) qs.set("type", params.type);
  if (params.max_cmc != null) qs.set("max_cmc", String(params.max_cmc));
  if (params.commander_id) qs.set("commander_id", params.commander_id);
  return get<Card[]>(`/cards?${qs.toString()}`);
}

export function getCommanders(
  params: { q?: string; colors?: string; sort?: CommanderSort; limit?: number } = {},
): Promise<Card[]> {
  const qs = new URLSearchParams();
  if (params.q) qs.set("q", params.q);
  if (params.colors) qs.set("colors", params.colors);
  if (params.sort) qs.set("sort", params.sort);
  if (params.limit != null) qs.set("limit", String(params.limit));
  const suffix = qs.toString();
  return get<Card[]>(`/cards/commanders${suffix ? `?${suffix}` : ""}`);
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

export function diagnoseDeck(
  cards: DeckEntry[],
  commander_id: string | null,
): Promise<DeckDiagnosis> {
  return post<DeckDiagnosis>("/deck/diagnose", { cards, commander_id });
}

/**
 * React Query hook for the Deck Doctor Diagnosis scorecard. Mount one-liner —
 * pass the working deck entries + commander id and feed `data` to
 * <DiagnosisGauge diagnosis={data ?? null} loading={isFetching} />.
 */
export function useDiagnosis(entries: DeckEntry[], commanderId: string | null) {
  const sig = entries
    .map((e) => `${e.id}:${e.quantity}`)
    .sort()
    .join(",");
  return useQuery({
    queryKey: ["diagnose", commanderId, sig],
    queryFn: () => diagnoseDeck(entries, commanderId),
    enabled: entries.length > 0,
    staleTime: 30_000,
  });
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

/**
 * Card Upgrade Finder: in-identity replacements for `targetId` that do the same
 * job but better. `efficiency` is the 0..1 slider (0 = closest functional match,
 * 1 = max efficiency); the toggles weight commander synergy and multimodal flex.
 */
export function findCardUpgrades(
  cards: DeckEntry[],
  commander_id: string | null,
  targetId: string,
  opts: {
    efficiency?: number;
    favorSynergy?: boolean;
    favorFlexibility?: boolean;
    limit?: number;
  } = {},
): Promise<UpgradeResponse> {
  const qs = new URLSearchParams({ target_id: targetId });
  if (opts.efficiency != null) qs.set("efficiency", String(opts.efficiency));
  if (opts.favorSynergy) qs.set("favor_synergy", "true");
  if (opts.favorFlexibility) qs.set("favor_flexibility", "true");
  if (opts.limit != null) qs.set("limit", String(opts.limit));
  return post<UpgradeResponse>(`/deck/card-upgrade?${qs.toString()}`, {
    cards,
    commander_id,
  });
}

/**
 * Deck-wide tune-up: the weakest cards in the deck (low commander synergy — the
 * cards typically cut from a precon) each paired with similar-but-better swaps.
 */
export function upgradeSweep(
  cards: DeckEntry[],
  commander_id: string,
  opts: { efficiency?: number; favorSynergy?: boolean; weak?: number } = {},
): Promise<UpgradeSweepResponse> {
  const qs = new URLSearchParams();
  if (opts.efficiency != null) qs.set("efficiency", String(opts.efficiency));
  if (opts.favorSynergy != null) qs.set("favor_synergy", String(opts.favorSynergy));
  if (opts.weak != null) qs.set("weak", String(opts.weak));
  return post<UpgradeSweepResponse>(`/deck/upgrade-sweep?${qs.toString()}`, {
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
  const res = await fetch(`${BASE}${path}`, { method: "DELETE", credentials: "include" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
}

async function put<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    credentials: "include",
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

// ---- SP12: fill-my-lands manabase tool ----
export function fillLands(
  cards: DeckEntry[],
  commander_id: string,
  maxPrice: number,
  template?: Record<string, number> | null,
): Promise<CompleteResponse> {
  const qs = new URLSearchParams({ max_price: String(maxPrice) });
  return post<CompleteResponse>(`/deck/lands?${qs.toString()}`, {
    cards,
    commander_id,
    template: template ?? null,
  });
}

// ---- SP8: deck doctor ----
export function postDeckComplete(
  cards: DeckEntry[],
  commander_id: string,
  template?: Record<string, number> | null,
): Promise<CompleteResponse> {
  return post<CompleteResponse>("/deck/complete", {
    cards,
    commander_id,
    template: template ?? null,
  });
}

// ---- Template system + dual-theme composite ----
export function getTemplates(): Promise<TemplatesResponse> {
  return get<TemplatesResponse>("/templates");
}

export function themeSuggest(
  commanderId: string,
  themes: string[],
  freeText: string,
  limit = 10,
  offset = 0,
): Promise<ThemeSuggestResponse> {
  const qs = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return post<ThemeSuggestResponse>(`/deck/theme-suggest?${qs.toString()}`, {
    commander_id: commanderId,
    themes,
    free_text: freeText,
  });
}

export function postDeckCuts(
  cards: DeckEntry[],
  commander_id: string,
  limit = 10,
): Promise<CutsResponse> {
  return post<CutsResponse>(`/deck/cuts?limit=${limit}`, { cards, commander_id });
}

// ---- Working-deck import (no auth) ----

export interface ParseImportUnresolved {
  line: string;
  name: string;
  quantity: number;
  suggestions: Card[];
}

export interface ParseImportResolved {
  card: Card;
  zone: string;
  quantity: number;
}

export interface ParseImportResult {
  resolved: ParseImportResolved[];
  unresolved: ParseImportUnresolved[];
  commander_id: string | null;
}

export function parseImport(text: string): Promise<ParseImportResult> {
  return post<ParseImportResult>("/deck/parse-import", { text });
}

// ---- IER breakdown (tiered — Mythic only gets factors) ----
export interface IerFactor {
  label: string;
  detail: string;
  value: number;
}

export interface IerBreakdownResponse {
  locked: boolean;
  ier: number;
  factors?: IerFactor[];
}

export function ierBreakdown(cardId: string): Promise<IerBreakdownResponse> {
  return get<IerBreakdownResponse>(`/cards/${encodeURIComponent(cardId)}/ier`);
}

// ---- SP9: synergy graph ----
export function postDeckGraph(
  cards: DeckEntry[],
  commander_id: string | null,
): Promise<GraphResponse> {
  return post<GraphResponse>("/deck/graph", { cards, commander_id });
}

// ---- SP11 (B): deck export ----

/** Fetch the backend and return the response body as plain text (not JSON). */
async function postText(path: string, body: unknown): Promise<string> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    credentials: "include",
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.text();
}

/**
 * Export the current working deck in the given format.
 *
 * @param entries     - The deck's card list (id + zone + quantity).
 * @param commanderId - The commander card id (or null).
 * @param format      - One of "text" | "moxfield" | "archidekt" | "manapool".
 * @returns           The formatted deck as a plain string.
 */
export function exportDeck(
  entries: DeckEntry[],
  commanderId: string | null,
  format: string,
): Promise<string> {
  return postText(`/deck/export?format=${encodeURIComponent(format)}`, {
    cards: entries,
    commander_id: commanderId,
  });
}
