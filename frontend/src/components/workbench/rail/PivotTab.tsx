"use client";

import { useState, type ReactNode } from "react";
import type { Card } from "@/lib/types";
import { formatSignal } from "@/lib/formatSignal";
import type { PivotCandidate, PivotEvidence, PivotMetrics, PivotResponse } from "@/lib/pivot";
import { CardSurface } from "@/components/card/CardSurface";
import { CardInteractive } from "@/components/card/CardInteractive";
import { EmptyState } from "./SuggestTab";

export interface PivotTabProps {
  commander: Card | null;
  /** False (gallery): scores were never requested. */
  active?: boolean;
  data?: PivotResponse | null;
  loading?: boolean;
  error?: boolean;
  includeAll?: boolean;
  onIncludeAll?: (value: boolean) => void;
}

const PIP_CLASS: Record<string, string> = {
  W: "text-mana-W",
  U: "text-mana-U",
  B: "text-mana-B",
  R: "text-mana-R",
  G: "text-mana-G",
};

const CHIP_ORDER = ["coverage", "edhrec_inclusion", "edhrec_synergy", "off_color", "popularity"];

function chipLabel(signal: string): string {
  switch (signal) {
    case "coverage":
      return "coverage";
    case "edhrec_inclusion":
      return "inclusion";
    case "edhrec_synergy":
      return "synergy";
    case "off_color":
      return "off-colour";
    case "popularity":
      return "popularity";
    default:
      return signal.trim() ? signal : "UNKNOWN";
  }
}

function shownNumber(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "UNKNOWN";
  return formatSignal(value, 2) || "UNKNOWN";
}

function EvidenceChips({ evidence }: { evidence: PivotEvidence[] }) {
  const rows = [...evidence].sort((a, b) => {
    const ia = CHIP_ORDER.indexOf(a.signal);
    const ib = CHIP_ORDER.indexOf(b.signal);
    return (ia === -1 ? CHIP_ORDER.length : ia) - (ib === -1 ? CHIP_ORDER.length : ib);
  });
  if (rows.length === 0) return null;
  return (
    <div className="mt-1 flex flex-wrap items-center gap-1.5">
      {rows.map((row, i) => (
        <span
          key={`${row.signal}-${i}`}
          data-reason-chip
          data-signal={row.signal}
          title={row.detail}
          className="inline-flex h-[18px] items-center gap-1 rounded border border-edge px-1.5 text-[11px] font-semibold leading-none text-zinc-400"
        >
          {chipLabel(row.signal)}
          <span className="font-mono font-normal text-zinc-300">{shownNumber(row.value)}</span>
        </span>
      ))}
    </div>
  );
}

function metricChips(metrics: PivotMetrics | null | undefined): PivotEvidence[] {
  if (!metrics) return [];
  const chips: PivotEvidence[] = [];
  if (typeof metrics.coverage === "number") {
    chips.push({ signal: "coverage", value: metrics.coverage, detail: "coverage" });
  }
  if (typeof metrics.inclusion_mean === "number") {
    chips.push({ signal: "edhrec_inclusion", value: metrics.inclusion_mean, detail: "inclusion" });
  }
  if (typeof metrics.synergy_mean === "number") {
    chips.push({ signal: "edhrec_synergy", value: metrics.synergy_mean, detail: "synergy" });
  }
  if (typeof metrics.off_color_count === "number") {
    chips.push({ signal: "off_color", value: metrics.off_color_count, detail: "off-colour count" });
  }
  return chips;
}

function Pips({ card }: { card: Card }) {
  const id = card.color_identity ?? [];
  if (id.length === 0) return <span className="text-[11px] text-zinc-400">colorless</span>;
  return (
    <span className="inline-flex gap-1">
      {id.map((c) => (
        <span key={c} className={["text-[11px] font-semibold", PIP_CLASS[c] ?? "text-zinc-300"].join(" ")}>
          {c}
        </span>
      ))}
    </span>
  );
}

function OffColorList({ candidate }: { candidate: PivotCandidate }) {
  const names = candidate.off_color_names ?? [];
  const count = candidate.metrics?.off_color_count;
  const knownCount = typeof count === "number";
  const more = knownCount ? Math.max(0, count - names.length) : 0;
  return (
    <div data-testid="pivot-off-color" className="mt-2 rounded border border-edge bg-ink/40 px-2 py-1.5">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-zinc-400">
        Off-colour · {knownCount ? count : "UNKNOWN"}
      </p>
      {knownCount && count === 0 ? (
        <p className="mt-1 text-[13px] leading-[18px] text-zinc-300">No off-colour cards.</p>
      ) : names.length === 0 ? (
        <p className="mt-1 text-[13px] leading-[18px] text-zinc-300">Names were not returned.</p>
      ) : (
        <ul className="mt-1 space-y-0.5">
          {names.map((name) => (
            <li key={name} className="truncate text-[13px] leading-[18px] text-zinc-200">
              {name}
            </li>
          ))}
        </ul>
      )}
      {more > 0 && (
        <p className="mt-1 text-[11px] leading-[14px] text-zinc-400">
          {more} more {more === 1 ? "name was" : "names were"} not returned.
        </p>
      )}
    </div>
  );
}

/** Pivot tab: ranked commanders from POST /deck/pivot. Selecting a row only lists off-colour cards. */
export function PivotTab({ commander, active, data, loading, error, includeAll = false, onIncludeAll }: PivotTabProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null);

  if (!commander) {
    return (
      <EmptyState testid="pivot-panel">
        No commander → <strong>Pick one</strong> (left) or <strong>paste a list</strong> (Import).
      </EmptyState>
    );
  }
  if (!active && data == null) {
    return (
      <EmptyState testid="pivot-panel">
        Pivot scores load from this deck. None are loaded here.
      </EmptyState>
    );
  }

  const currentName = data?.current?.commander?.name || commander.name || "UNKNOWN";
  const baseline = data?.current?.metrics;
  const candidates = data?.candidates ?? [];

  const toggle = (
    <label className="inline-flex h-8 cursor-pointer items-center gap-1.5 text-[13px] text-zinc-200">
      <input
        type="checkbox"
        data-testid="pivot-include-all"
        className="accent-[#ffd24a]"
        checked={includeAll}
        disabled={!onIncludeAll}
        title="Also list commanders that do not beat the current one"
        onChange={(e) => onIncludeAll?.(e.target.checked)}
      />
      Include all
    </label>
  );

  let body: ReactNode;
  if (error && data == null) {
    body = <EmptyState>The pivot request failed.</EmptyState>;
  } else if (data == null) {
    body = (
      <p className="px-3 py-4 text-[13px] text-zinc-400">
        {loading ? "Ranking commanders…" : "No pivot scores yet."}
      </p>
    );
  } else if (candidates.length === 0) {
    const noBaseline = data.current == null || data.current.metrics == null;
    body = (
      <EmptyState>
        {includeAll
          ? "No alternative commanders were returned."
          : noBaseline
            ? `${currentName} has no EDHREC page, so there is no baseline score. No alternative commanders were returned.`
            : `No candidate beats ${currentName}.`}
      </EmptyState>
    );
  } else {
    body = (
      <CardSurface id="rail-pivot" orientation="column" label="Pivot candidates" className="min-h-0 flex-1 overflow-y-auto">
        <ul>
          {candidates.map((c, idx) => {
            const card = c.commander;
            const id = card?.id ?? "";
            const open = selectedId === id && id !== "";
            const score = shownNumber(c.metrics?.score);
            const reason = (c.reason ?? "").trim() || "UNKNOWN";
            return (
              <li
                key={id || `${card?.name ?? "unknown"}-${idx}`}
                data-testid="pivot-row"
                data-card-id={id || undefined}
                data-better={c.better_than_current == null ? undefined : String(c.better_than_current)}
                className="border-b border-edge/70 px-3 py-2.5 last:border-b-0"
              >
                <div className="flex items-start gap-3">
                  {card ? (
                    <CardInteractive
                      card={card}
                      size="thumb"
                      context="pivot"
                      surfaceId="rail-pivot"
                      primary={() => setSelectedId(open ? null : id)}
                      className="mt-0.5 shrink-0"
                      state={{ ierPill: null }}
                    />
                  ) : (
                    <span className="mt-0.5 text-[11px] text-zinc-400">UNKNOWN</span>
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-start gap-2">
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[13px] font-semibold text-zinc-100">{card?.name ?? "UNKNOWN"}</p>
                        <p className="mt-0.5 flex flex-wrap items-center gap-1.5">
                          {card && <Pips card={card} />}
                          <span className="text-[11px] tabular-nums text-zinc-400">score {score}</span>
                        </p>
                      </div>
                      <button
                        type="button"
                        data-testid="pivot-list"
                        title="List off-colour cards"
                        aria-expanded={open}
                        aria-label={`List off-colour cards: ${card?.name ?? "UNKNOWN"}`}
                        onClick={() => setSelectedId(open ? null : id)}
                        className="flex h-9 shrink-0 items-center justify-center rounded border border-edge px-2 text-[13px] font-semibold text-zinc-200 hover:border-accent/60 hover:text-accent [@media(pointer:coarse)]:h-11"
                      >
                        {open ? "Hide" : "List"}
                      </button>
                    </div>
                    <p data-reason-sentence className="mt-1.5 text-[13px] leading-[18px] text-zinc-200">
                      {reason}
                    </p>
                    <EvidenceChips evidence={c.evidence ?? []} />
                    {c.better_than_current === false && (
                      <p className="mt-1 text-[11px] leading-[14px] text-zinc-400">Does not beat the baseline.</p>
                    )}
                    {open && <OffColorList candidate={c} />}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      </CardSurface>
    );
  }

  const scoreText = data
    ? baseline
      ? shownNumber(baseline.score)
      : data.current
        ? null
        : "UNKNOWN"
    : null;

  return (
    <section data-testid="pivot-panel" aria-label="Pivot" className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-edge px-3 py-2">
        {toggle}
        {typeof data?.deck_size === "number" && (
          <span title="The commander and basic lands carry no commander signal, so they are not scored" className="text-[11px] text-zinc-400">{data.deck_size} non-basic cards scored</span>
        )}
      </div>
      {data && (
        <div data-testid="pivot-baseline" className="border-b border-edge px-3 py-2">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-zinc-400">Baseline</p>
          <p className="truncate text-[13px] font-semibold text-zinc-100">{currentName}</p>
          {scoreText == null ? (
            <p className="mt-0.5 text-[13px] leading-[18px] text-zinc-300">
              No EDHREC page for {currentName} — no baseline score.
            </p>
          ) : (
            <p className="mt-0.5 text-[13px] tabular-nums text-zinc-200">score {scoreText}</p>
          )}
          <EvidenceChips evidence={metricChips(baseline)} />
        </div>
      )}
      {body}
    </section>
  );
}
