// Shared data contract — keep in lockstep with backend/app/models.py.

export interface User {
  id: number;
  username: string;
  is_admin?: boolean;
  /** Subscription tier. "mythic" unlocks the IER algorithm reveal. Placeholder
   * until a real tier/Patreon system exists — admins are treated as mythic. */
  tier?: "free" | "mythic";
}

export interface Card {
  id: string;
  name: string;
  cmc: number;
  type_line: string;
  oracle_text: string;
  colors: string[];
  color_identity: string[];
  power: string | null;
  toughness: string | null;
  keywords: string[];
  image_uris: { normal?: string } | null;
  ier: number | null;
  mechanic_tags: string[];
  /** Fine-grained semantic tags (e:gain_life, k:lifelink, …) — the same vocabulary
   * template themes use, so the Engine Board can match a card to an engine. */
  semantic_tags?: string[];
  /** True if this card can reasonably end the game on its own (a win condition). */
  wincon?: boolean;
  /** Commander popularity = corpus decks led by this card (commanders only). */
  deck_count?: number | null;
}

export type CommanderSort = "popularity" | "name" | "ier";

export interface SynergyEdge {
  card_a: string;
  card_b: string;
  css: number;
  der: number;
  lift: boolean;
}

// ---- SP5 suggestions ----
export interface Reason {
  signal: string; // "edhrec" | "cooccurrence" | "synergy" | "engine" | "staple"
  detail: string;
  value: number;
}

export interface Suggestion {
  card: Card;
  score: number;
  reasons: Reason[];
}

export interface SuggestionResponse {
  tier: "edhrec" | "cooccurrence" | "color_staple";
  suggestions: Suggestion[];
}

// ---- Card Upgrade Finder ----
export interface UpgradeOption {
  card: Card;
  score: number;
  efficiency_gain: number; // candidate IER - target IER (can be negative)
  similarity: number; // 0..1 functional similarity to the target
  reasons: Reason[];
}

export interface UpgradeResponse {
  target: Card | null;
  options: UpgradeOption[];
}

// ---- SP4 relationship explorer ----
export type RelationshipAxis = "similar" | "synergy" | "cooccurrence";

export interface RelationshipNeighbor {
  card: Card;
  metric: number;
}

export interface EngineGroup {
  engine_id: string;
  kind: string;
  asserted: boolean;
  candidate: boolean;
  members: Card[];
}

export interface PairScoreFull {
  a: string;
  b: string;
  ier_a: number;
  ier_b: number;
  css: number;
  der: number;
  lift: boolean;
  relationship: {
    similarity: number;
    synergy_ab: number;
    synergy_ba: number;
    anti_synergy: number;
    combo: boolean;
    combo_id: string | null;
  } | null;
  cooccurrence: {
    co_count: number;
    lift: number;
    jaccard: number;
    support: number;
  } | null;
}

// ---- SP6: deck persistence ----
export interface DeckSummary {
  id: string;
  name: string;
  commander_id: string | null;
  card_count: number;
  updated_at: string;
}

export interface DeckCardOut {
  card: Card;
  zone: string;
  quantity: number;
}

export interface DeckDetail {
  id: string;
  name: string;
  commander_id: string | null;
  created_at: string;
  updated_at: string;
  cards: DeckCardOut[];
}

export interface ImportResult {
  deck: DeckDetail;
  unresolved: string[];
}

// ---- SP7: Commander Spellbook ----
export interface SpellbookCombo {
  combo_id: string;
  identity: string;
  popularity: number | null;
  description: string;
  produces: string[];
  mana_needed: string;
  members: Card[];
}

export interface NearCombo {
  combo: SpellbookCombo;
  missing: Card;
}

export interface DeckCombos {
  complete: SpellbookCombo[];
  near: NearCombo[];
}

// ---- SP8: deck doctor ----
export interface CompletionAdd {
  card: Card;
  zone: string;
  quantity: number;
  reason: string;
}

export interface CompleteResponse {
  added: CompletionAdd[];
  final_size: number;
}

export interface Cut {
  card: Card;
  contribution: number;
  reasons: Reason[];
}

export interface CutsResponse {
  cuts: Cut[];
}

// ---- SP9: synergy graph ----
export interface GraphNode {
  id: string;
  name: string;
  ier: number | null;
  category: string;
  image: string | null;
}

export interface GraphEdge {
  a: string;
  b: string;
  kind: "combo" | "synergy" | "cooccurrence";
  weight: number;
}

export interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface DeckEntry {
  id: string;
  zone: string;
  quantity: number;
}

// ---- Template system + dual-theme composite ----
export interface TemplateInfo {
  id: string;
  name: string;
  source: string;
  counts: Record<string, number>; // doctor keys: land/ramp/card_draw/removal/board_wipe
  notes: string;
}

export interface ThemeInfo {
  id: string;
  label: string;
  tags: string[];
}

export interface TemplatesResponse {
  templates: TemplateInfo[];
  themes: ThemeInfo[];
}

export interface ThemeSuggestion {
  card: Card;
  score: number;
  themes_matched: number;
}

export interface ThemeSuggestResponse {
  cards: ThemeSuggestion[];
  total: number;
  has_more: boolean;
}

/** The 5 Deck-Doctor composition categories, in display order. */
export const TEMPLATE_CATEGORIES = [
  "land",
  "ramp",
  "card_draw",
  "removal",
  "board_wipe",
] as const;
export type TemplateCategory = (typeof TEMPLATE_CATEGORIES)[number];

export interface Vital {
  label: string;
  score: number; // 0–100
}

export interface DeckDiagnosis {
  score: number; // 0–100 overall
  verdict: string; // CRITICAL | UNSTABLE | FAIR | STABLE | OPTIMAL | "—"
  vitals: Vital[];
}

export interface DeckAnalysis {
  card_count: number;
  mana_curve: { cmc: number; count: number }[];
  color_pips: Record<string, number>;
  type_counts: Record<string, number>;
  efficiency: number;
  impact: number;
  average_playability: number;
  score: number;
  bracket: number;
  bracket_reasons: string[];
  top_synergies: SynergyEdge[];
  keepable_hand_pct: number;
}
