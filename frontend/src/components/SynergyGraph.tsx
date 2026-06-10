"use client";

/**
 * SP9 — full-screen deck synergy graph (d3-force on <canvas>). SCAFFOLD — implement per
 * roadmap §9.2. Dependencies d3-force + @types/d3-force are already in package.json.
 *
 * Overlay: fixed inset-0 z-[130] bg-ink/95; ✕ top-right + ESC close. Opened from a header
 * button `🕸 Graph` in page.tsx (enabled when deck ≥ 5 cards).
 *
 * Data: react-query on deck signature → postDeckGraph(entries, commanderId).
 *
 * Simulation (sim in a ref; build in useEffect on data change; stop() on cleanup):
 *   forceSimulation(nodes)
 *     .force("link", forceLink(edges).id(d => d.id)
 *         .distance(l => 40 + 80 * (1 - l.weight)).strength(l => 0.2 + 0.6 * l.weight))
 *     .force("charge", forceManyBody().strength(-140))
 *     .force("collide", forceCollide(26))
 *     .force("center", forceCenter(w / 2, h / 2))
 * Mutate copies of the data (d3-force writes x/y/vx/vy onto nodes).
 *
 * Canvas render on every "tick" (devicePixelRatio-scaled):
 * - edges first: combo #e879f9 width 2.5; synergy #c9a227 width 1 + weight;
 *   cooccurrence #38bdf8 width 1 alpha 0.6.
 * - nodes: r=20 circle filled by category color (land #9aa0a6, ramp #22c55e,
 *   card_draw #3b82f6, removal #ef4444, board_wipe #f97316, counters #a78bfa,
 *   tokens #facc15, synergy #e5e7eb, commander #c9a227 with r=26 gold ring),
 *   name below (10px, truncate 14 chars), IER inside the circle.
 *
 * Interaction (pointer events on the canvas — do NOT add d3-selection/d3-drag):
 * - hover: nearest node within r+4 → highlight node + its edges, others alpha 0.15;
 *   absolutely-positioned tooltip div (name, category, IER, degree).
 * - drag: set node.fx/fy while down; simulation.alphaTarget(0.3) during, 0 + clear fx/fy on
 *   release.
 * - click (movement ≤ 4px): getCard(node.id) → useRelationshipStore.open(card, "synergy")
 *   and onClose().
 * - Legend bottom-left (edge kinds + category colors); footer "N cards · M edges".
 * data-testid: "synergy-graph", canvas "graph-canvas".
 */
import type { Card, DeckEntry } from "@/lib/types";

export function SynergyGraph({
  isOpen,
  onClose,
  commander,
  entries,
}: {
  isOpen: boolean;
  onClose: () => void;
  commander: Card | null;
  entries: DeckEntry[];
}) {
  if (!isOpen) return null;
  void onClose;
  void commander;
  void entries;
  // TODO(SP9): implement per the docstring above.
  return null;
}
