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
