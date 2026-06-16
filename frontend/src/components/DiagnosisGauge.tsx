"use client";

import type { DeckDiagnosis } from "@/lib/types";

/**
 * DiagnosisGauge — the headline Deck Doctor neon gauge (design-previews/option-7).
 *
 * Presentational only: a circular SVG ring (cyan→magenta→gold gradient stroke)
 * showing the 0–100 Diagnosis score + verdict, with the five vitals as small
 * neon meter bars. No data fetching — feed it `diagnosis` (use `useDiagnosis`).
 */

const GOLD = "#ffd24a";
const MAGENTA = "#ff2bd6";
const CYAN = "#00eeff";
const INK_DIM = "#c8b6ff";
const INK_FAINT = "#8d7ec4";

// r=43 ring → circumference; the fill stroke-dasharray "arc 999" reveals
// `arc` of the circumference proportional to the score (matches option-7).
const RADIUS = 43;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS; // ≈ 270

const VERDICT_COLOR: Record<string, string> = {
  OPTIMAL: "#21ff9e",
  STABLE: "#bfffe0",
  FAIR: GOLD,
  UNSTABLE: "#ffae00",
  CRITICAL: "#ff3b6b",
};

function Vital({ label, score }: { label: string; score: number }) {
  return (
    <div className="flex items-center gap-3">
      <span
        className="w-24 flex-none text-[10px] uppercase tracking-[1.5px]"
        style={{ color: INK_DIM }}
      >
        {label}
      </span>
      <span className="relative h-[7px] flex-1 overflow-hidden rounded border border-accent/15 bg-violet-500/20">
        <i
          className="absolute inset-y-0 left-0 rounded transition-[width] duration-700 ease-out"
          style={{
            width: `${Math.max(0, Math.min(100, score))}%`,
            background: `linear-gradient(90deg, ${CYAN}, ${MAGENTA}, ${GOLD})`,
            boxShadow: "0 0 10px rgba(255,210,74,.5)",
          }}
        />
      </span>
      <span
        className="w-8 flex-none text-right text-sm font-black text-accent"
        style={{ textShadow: "0 0 18px rgba(255,210,74,.55)" }}
      >
        {score}
      </span>
    </div>
  );
}

export default function DiagnosisGauge({
  diagnosis,
  loading = false,
}: {
  diagnosis: DeckDiagnosis | null;
  loading?: boolean;
}) {
  const score = diagnosis?.score ?? 0;
  const verdict = diagnosis?.verdict ?? "—";
  const vitals = diagnosis?.vitals ?? [];
  const arc = (Math.max(0, Math.min(100, score)) / 100) * CIRCUMFERENCE;
  const verdictColor = VERDICT_COLOR[verdict] ?? GOLD;

  return (
    <div
      className="relative rounded-2xl border-2 border-accent p-7"
      style={{
        background: "linear-gradient(180deg,rgba(43,15,84,.9),rgba(16,7,42,.95))",
        boxShadow:
          "0 0 50px rgba(255,170,0,.3),inset 0 0 36px rgba(255,43,214,.07),0 24px 60px rgba(0,0,0,.55)",
      }}
    >
      <div className="mb-4 flex items-center justify-between">
        <span
          className="text-[11px] uppercase tracking-[1px] text-amber-100"
          style={{ textShadow: "1px 1px 0 #5e3510,0 0 12px rgba(255,174,0,.5)" }}
        >
          Deck Doctor Diagnosis
        </span>
        <span
          className="text-[11px] uppercase tracking-[2px]"
          style={{ color: INK_FAINT }}
        >
          {loading ? "Analyzing…" : "℞ Diagnostic"}
        </span>
      </div>

      <div className="flex items-center gap-6">
        {/* GAUGE */}
        <div className="relative h-44 w-44 flex-none">
          <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90">
            <defs>
              <linearGradient id="diaggaugegrad" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor={CYAN} />
                <stop offset="50%" stopColor={MAGENTA} />
                <stop offset="100%" stopColor={GOLD} />
              </linearGradient>
            </defs>
            <circle
              cx="50"
              cy="50"
              r={RADIUS}
              fill="none"
              stroke="rgba(154,75,255,.2)"
              strokeWidth="7"
            />
            <circle
              cx="50"
              cy="50"
              r="35"
              fill="none"
              stroke="rgba(255,210,74,.28)"
              strokeWidth="5"
              strokeDasharray="1 6"
            />
            <circle
              cx="50"
              cy="50"
              r={RADIUS}
              fill="none"
              stroke="url(#diaggaugegrad)"
              strokeWidth="8"
              strokeLinecap="round"
              strokeDasharray={`${arc} 999`}
              style={{
                filter: "drop-shadow(0 0 9px rgba(255,210,74,.8))",
                transition: "stroke-dasharray 1.4s cubic-bezier(.3,.8,.3,1)",
              }}
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
            <div
              className="text-[34px] font-black leading-none text-amber-100"
              style={{ textShadow: "0 0 22px rgba(255,174,0,.7)" }}
            >
              {score}
              <sup className="align-super text-xs text-sky-200">/100</sup>
            </div>
            <div className="mt-2 text-[10px] uppercase tracking-[3px] text-accent">
              Diagnosis
            </div>
          </div>
        </div>

        {/* VERDICT + VITALS */}
        <div className="min-w-0 flex-1">
          <div
            className="text-[22px] font-black uppercase tracking-tight"
            style={{ color: verdictColor, textShadow: `0 0 16px ${verdictColor}66` }}
          >
            {verdict}
          </div>
          <div className="mb-4 mt-2 text-[13px] tracking-[1px]" style={{ color: INK_DIM }}>
            {diagnosis ? "Engine vitals" : "Add cards to diagnose your deck"}
          </div>
          <div className="flex flex-col gap-[9px]">
            {vitals.map((v) => (
              <Vital key={v.label} label={v.label} score={v.score} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
