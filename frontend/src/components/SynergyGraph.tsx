"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  type Simulation,
  type SimulationNodeDatum,
} from "d3-force";
import { getCard, postDeckGraph } from "@/lib/api";
import { useRelationshipStore } from "@/store/relationship";
import type { Card, DeckEntry, GraphEdge, GraphNode } from "@/lib/types";

const CATEGORY_COLOR: Record<string, string> = {
  land: "#9aa0a6",
  ramp: "#22c55e",
  card_draw: "#3b82f6",
  removal: "#ef4444",
  board_wipe: "#f97316",
  counters: "#a78bfa",
  tokens: "#facc15",
  synergy: "#e5e7eb",
  commander: "#ffd24a",
};
const EDGE_COLOR: Record<string, string> = {
  combo: "#ff2bd6",
  synergy: "#ffd24a",
  cooccurrence: "#00eeff",
};

interface SimNode extends SimulationNodeDatum, GraphNode {}
interface SimLink {
  source: SimNode;
  target: SimNode;
  kind: GraphEdge["kind"];
  weight: number;
}

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
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const simRef = useRef<Simulation<SimNode, undefined> | null>(null);
  const nodesRef = useRef<SimNode[]>([]);
  const linksRef = useRef<SimLink[]>([]);
  const hoverRef = useRef<SimNode | null>(null);
  const openExplorer = useRelationshipStore((s) => s.open);
  const [tooltip, setTooltip] = useState<{ x: number; y: number; node: SimNode } | null>(null);

  const deckSig = entries.map((e) => e.id).sort().join(",");
  const { data } = useQuery({
    queryKey: ["deck-graph", commander?.id ?? null, deckSig],
    queryFn: () => postDeckGraph(entries, commander?.id ?? null),
    enabled: isOpen && entries.length > 0,
    staleTime: 30_000,
  });

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [onClose]);

  useEffect(() => {
    if (!isOpen || !data) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const w = window.innerWidth;
    const h = window.innerHeight;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    const ctx = canvas.getContext("2d")!;
    ctx.scale(dpr, dpr);

    const nodes: SimNode[] = data.nodes.map((n) => ({ ...n }));
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const links: SimLink[] = data.edges
      .map((e) => ({
        source: byId.get(e.a)!,
        target: byId.get(e.b)!,
        kind: e.kind,
        weight: e.weight,
      }))
      .filter((l) => l.source && l.target);
    nodesRef.current = nodes;
    linksRef.current = links;

    const degree = new Map<string, number>();
    links.forEach((l) => {
      degree.set(l.source.id, (degree.get(l.source.id) ?? 0) + 1);
      degree.set(l.target.id, (degree.get(l.target.id) ?? 0) + 1);
    });

    function draw() {
      ctx.clearRect(0, 0, w, h);
      const hover = hoverRef.current;
      const lit = new Set<string>();
      if (hover) {
        lit.add(hover.id);
        links.forEach((l) => {
          if (l.source.id === hover.id) lit.add(l.target.id);
          if (l.target.id === hover.id) lit.add(l.source.id);
        });
      }
      // edges
      for (const l of links) {
        const dim = hover && !(lit.has(l.source.id) && lit.has(l.target.id));
        ctx.globalAlpha = dim ? 0.08 : l.kind === "cooccurrence" ? 0.6 : 0.9;
        ctx.strokeStyle = EDGE_COLOR[l.kind];
        ctx.lineWidth = l.kind === "combo" ? 2.5 : l.kind === "synergy" ? 1 + l.weight : 1;
        ctx.beginPath();
        ctx.moveTo(l.source.x!, l.source.y!);
        ctx.lineTo(l.target.x!, l.target.y!);
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
      // nodes
      for (const n of nodes) {
        const isCmd = n.category === "commander";
        const r = isCmd ? 26 : 20;
        const dim = hover && !lit.has(n.id);
        ctx.globalAlpha = dim ? 0.2 : 1;
        ctx.beginPath();
        ctx.arc(n.x!, n.y!, r, 0, Math.PI * 2);
        ctx.fillStyle = CATEGORY_COLOR[n.category] ?? "#e5e7eb";
        ctx.fill();
        if (isCmd) {
          ctx.lineWidth = 3;
          ctx.strokeStyle = "#fde68a";
          ctx.stroke();
        }
        // IER inside
        if (n.ier != null) {
          ctx.fillStyle = "#0b0b10";
          ctx.font = "bold 10px sans-serif";
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(String(n.ier), n.x!, n.y!);
        }
        // label below
        ctx.fillStyle = "#cbd5e1";
        ctx.font = "10px sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        const label = n.name.length > 14 ? n.name.slice(0, 13) + "…" : n.name;
        ctx.fillText(label, n.x!, n.y! + r + 2);
      }
      ctx.globalAlpha = 1;
    }

    const sim = forceSimulation<SimNode>(nodes)
      .force(
        "link",
        forceLink<SimNode, SimLink>(links)
          .id((d) => d.id)
          .distance((l) => 40 + 80 * (1 - l.weight))
          .strength((l) => 0.2 + 0.6 * l.weight),
      )
      .force("charge", forceManyBody().strength(-140))
      .force("collide", forceCollide(26))
      .force("center", forceCenter(w / 2, h / 2))
      .on("tick", draw);
    simRef.current = sim;

    // ---- pointer interaction ----
    function nearest(px: number, py: number): SimNode | null {
      let best: SimNode | null = null;
      let bestD = Infinity;
      for (const n of nodes) {
        const r = n.category === "commander" ? 26 : 20;
        const dx = px - (n.x ?? 0);
        const dy = py - (n.y ?? 0);
        const d = Math.hypot(dx, dy);
        if (d < r + 4 && d < bestD) {
          best = n;
          bestD = d;
        }
      }
      return best;
    }

    let dragNode: SimNode | null = null;
    let downPos: { x: number; y: number } | null = null;

    const el = canvas;
    function pos(e: PointerEvent) {
      const rect = el.getBoundingClientRect();
      return { x: e.clientX - rect.left, y: e.clientY - rect.top };
    }
    function onDown(e: PointerEvent) {
      const p = pos(e);
      downPos = p;
      const n = nearest(p.x, p.y);
      if (n) {
        dragNode = n;
        n.fx = n.x;
        n.fy = n.y;
        sim.alphaTarget(0.3).restart();
        el.setPointerCapture(e.pointerId);
      }
    }
    function onMove(e: PointerEvent) {
      const p = pos(e);
      if (dragNode) {
        dragNode.fx = p.x;
        dragNode.fy = p.y;
        return;
      }
      const n = nearest(p.x, p.y);
      hoverRef.current = n;
      setTooltip(n ? { x: e.clientX, y: e.clientY, node: n } : null);
      draw();
    }
    function onUp(e: PointerEvent) {
      const p = pos(e);
      const moved = downPos ? Math.hypot(p.x - downPos.x, p.y - downPos.y) : 99;
      if (dragNode) {
        dragNode.fx = null;
        dragNode.fy = null;
        sim.alphaTarget(0);
      }
      if (moved <= 4) {
        const n = nearest(p.x, p.y);
        if (n) {
          getCard(n.id)
            .then((card) => {
              openExplorer(card, "synergy");
              onClose();
            })
            .catch(() => {});
        }
      }
      dragNode = null;
      downPos = null;
    }
    canvas.addEventListener("pointerdown", onDown);
    canvas.addEventListener("pointermove", onMove);
    canvas.addEventListener("pointerup", onUp);

    return () => {
      sim.stop();
      canvas.removeEventListener("pointerdown", onDown);
      canvas.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("pointerup", onUp);
    };
  }, [isOpen, data, onClose, openExplorer]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[130] bg-ink/95" data-testid="synergy-graph">
      <canvas ref={canvasRef} data-testid="graph-canvas" className="absolute inset-0" />

      <button
        onClick={onClose}
        className="absolute right-4 top-4 z-10 rounded-lg border border-accent/50 bg-ink/80 px-3 py-1.5
                   text-sm text-accent backdrop-blur-sm transition hover:bg-accent/10"
      >
        ✕ Close
      </button>

      {/* Legend */}
      <div className="absolute bottom-4 left-4 z-10 rounded-lg border border-accent/30 bg-ink/80 p-3 text-[10px] backdrop-blur-sm">
        <p className="mb-1 font-display text-[9px] uppercase tracking-wider text-accent">Edges</p>
        <div className="mb-2 flex flex-col gap-0.5">
          <span style={{ color: EDGE_COLOR.combo }}>━ combo</span>
          <span style={{ color: EDGE_COLOR.synergy }}>━ synergy</span>
          <span style={{ color: EDGE_COLOR.cooccurrence }}>━ played together</span>
        </div>
        <p className="mb-1 font-display text-[9px] uppercase tracking-wider text-accent">Roles</p>
        <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
          {Object.entries(CATEGORY_COLOR).map(([cat, col]) => (
            <span key={cat} style={{ color: col }}>
              ● {cat.replace("_", " ")}
            </span>
          ))}
        </div>
      </div>

      {/* Footer count */}
      {data && (
        <div className="absolute bottom-4 right-4 z-10 rounded-lg border border-accent/30 bg-ink/80 px-3 py-1.5 text-[10px] text-zinc-400 backdrop-blur-sm">
          {data.nodes.length} cards · {data.edges.length} edges · drag to rearrange · click to explore
        </div>
      )}

      {/* Tooltip */}
      {tooltip && (
        <div
          className="pointer-events-none absolute z-20 rounded border border-accent/40 bg-ink/90 px-2 py-1 text-[10px] text-zinc-200 shadow-neon backdrop-blur-sm"
          style={{ left: tooltip.x + 12, top: tooltip.y + 12 }}
        >
          <p className="font-semibold text-accent">{tooltip.node.name}</p>
          <p className="text-zinc-500">
            {tooltip.node.category}
            {tooltip.node.ier != null && ` · IER ${tooltip.node.ier}`}
          </p>
        </div>
      )}
    </div>
  );
}
