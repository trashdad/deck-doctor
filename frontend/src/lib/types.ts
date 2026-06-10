// Shared data contract — keep in lockstep with backend/app/models.py.

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
}

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

export interface DeckEntry {
  id: string;
  zone: string;
  quantity: number;
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
