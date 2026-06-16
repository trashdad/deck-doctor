"use client";

import type { DeckAnalysis, DeckDiagnosis } from "@/lib/types";
import { MANA_COLORS } from "@/lib/zones";
import { Gauge } from "./Gauge";
import DiagnosisGauge from "./DiagnosisGauge";

function ManaCurve({ curve }: { curve: { cmc: number; count: number }[] }) {
  const max = Math.max(1, ...curve.map((b) => b.count));
  return (
    <div className="flex h-24 items-end gap-1">
      {curve.map((b) => (
        <div key={b.cmc} className="flex flex-1 flex-col items-center">
          <div
            className="w-full rounded-t bg-accent2"
            style={{ height: `${(b.count / max) * 100}%` }}
            title={`CMC ${b.cmc}: ${b.count}`}
          />
          <span className="mt-1 text-[10px] text-zinc-500">{b.cmc}</span>
        </div>
      ))}
      {curve.length === 0 && (
        <p className="w-full text-center text-xs text-zinc-600">no spells yet</p>
      )}
    </div>
  );
}

function ColorPips({ pips }: { pips: Record<string, number> }) {
  const total = Object.values(pips).reduce((a, b) => a + b, 0) || 1;
  return (
    <div className="space-y-1">
      {Object.entries(pips).map(([sym, n]) => (
        <div key={sym} className="flex items-center gap-2 text-xs">
          <span
            className="inline-block h-3 w-3 rounded-full border border-black/30"
            style={{ background: MANA_COLORS[sym] ?? "#888" }}
          />
          <div className="h-2 flex-1 overflow-hidden rounded bg-edge">
            <div
              className="h-full"
              style={{ width: `${(n / total) * 100}%`, background: MANA_COLORS[sym] ?? "#888" }}
            />
          </div>
          <span className="w-6 text-right text-zinc-400">{n}</span>
        </div>
      ))}
    </div>
  );
}

export function StatsSidebar({
  analysis,
  diagnosis,
  diagnosisLoading,
}: {
  analysis: DeckAnalysis | null;
  diagnosis?: DeckDiagnosis | null;
  diagnosisLoading?: boolean;
}) {
  if (!analysis) {
    return (
      <aside className="w-80 shrink-0 space-y-4 border-l border-accent/30 bg-panel/80 p-4 backdrop-blur-sm">
        <DiagnosisGauge diagnosis={diagnosis ?? null} loading={diagnosisLoading} />
        <p className="text-sm text-zinc-500">Add cards to see the deck engine.</p>
      </aside>
    );
  }
  return (
    <aside className="w-80 shrink-0 space-y-5 overflow-y-auto border-l border-accent/30 bg-panel/80 p-4 backdrop-blur-sm scrollbar-thin">
      {/* The headline Deck Doctor Diagnosis (0–100) sits above the engine stats. */}
      <DiagnosisGauge diagnosis={diagnosis ?? null} loading={diagnosisLoading} />
      <div className="h-px bg-accent/20" />
      <div className="flex items-center justify-between">
        <h2 className="arcade-bevel text-sm">Deck Engine</h2>
        <span className="rounded-full border border-cyan/50 bg-cyan/10 px-3 py-1 text-xs text-cyan">
          Bracket {analysis.bracket}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <Gauge label="Efficiency" value={analysis.efficiency} max={10} />
        <Gauge label="Impact" value={analysis.impact} max={10} />
      </div>
      <div className="flex items-center justify-between rounded-lg border border-accent/30 bg-panel2/70 px-3 py-2">
        <span className="font-display text-[9px] uppercase tracking-wider text-accent">Score</span>
        <span className="text-2xl font-bold text-accent">{analysis.score}</span>
        <span className="text-xs text-zinc-500">/ 1000</span>
      </div>

      <section>
        <h3 className="mb-2 font-display text-[9px] uppercase tracking-wider text-accent">Mana Curve</h3>
        <ManaCurve curve={analysis.mana_curve} />
      </section>

      <section>
        <h3 className="mb-2 font-display text-[9px] uppercase tracking-wider text-accent">Color Identity</h3>
        <ColorPips pips={analysis.color_pips} />
      </section>

      <section className="space-y-1 text-xs text-zinc-400">
        <div className="flex justify-between">
          <span>Playability (ramp/draw by T1)</span>
          <span className="text-zinc-200">{analysis.average_playability}%</span>
        </div>
        <div className="flex justify-between">
          <span>Keepable hand (≥3 lands)</span>
          <span className="text-zinc-200">{analysis.keepable_hand_pct}%</span>
        </div>
      </section>

      {analysis.top_synergies.length > 0 && (
        <section>
          <h3 className="mb-2 font-display text-[9px] uppercase tracking-wider text-accent">
            Top Synergies (DER)
          </h3>
          <ul className="space-y-1 text-xs">
            {analysis.top_synergies.slice(0, 6).map((e) => (
              <li
                key={`${e.card_a}-${e.card_b}`}
                className="flex items-center justify-between rounded border border-edge bg-panel2/70 px-2 py-1"
              >
                <span className="truncate text-zinc-300">
                  {e.card_a} + {e.card_b}
                </span>
                <span className="ml-2 shrink-0 text-accent">
                  {e.der.toFixed(1)}
                  {e.lift && <span className="ml-1 text-red-400">⚡</span>}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {analysis.bracket_reasons.length > 0 && (
        <section>
          <h3 className="mb-1 font-display text-[9px] uppercase tracking-wider text-accent">
            Bracket Flags
          </h3>
          <div className="flex flex-wrap gap-1">
            {analysis.bracket_reasons.map((r) => (
              <span
                key={r}
                className="rounded bg-red-500/15 px-2 py-0.5 text-[11px] text-red-300"
              >
                {r}
              </span>
            ))}
          </div>
        </section>
      )}
    </aside>
  );
}
