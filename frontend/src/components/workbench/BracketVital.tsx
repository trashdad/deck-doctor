"use client";

export interface BracketVitalProps {
  /** null until an analysis has run. */
  bracket: { floor: number; flags: string[] } | null;
  onFlagClick?: (flag: string) => void;
  /** Deck header row 1: one line; flags beyond the second collapse into "+N" (the title lists them). */
  compact?: boolean;
  className?: string;
}

const FLOOR_COPY = "This is a floor from card flags, not a verdict. Your pod decides the bracket.";

/**
 * "≥ Bracket N · fast mana, 1 combo pair" — always "at least", never a bare
 * number, never a percentage (§5.3). Flags are chips; clicking one highlights
 * the triggering cards on the board (the caller does the highlighting).
 */
export function BracketVital({ bracket, onFlagClick, compact, className }: BracketVitalProps) {
  const flags = bracket?.flags ?? [];
  const shown = compact ? flags.slice(0, 2) : flags;
  const hidden = flags.length - shown.length;
  return (
    <div
      data-testid="bracket-vital"
      className={[
        "flex min-w-0 items-center gap-x-2 gap-y-1",
        compact ? "flex-nowrap overflow-hidden" : "flex-wrap",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      title={flags.length ? `${FLOOR_COPY} Flags: ${flags.join(", ")}` : FLOOR_COPY}
    >
      <span className="shrink-0 whitespace-nowrap text-[13px] font-semibold text-zinc-100">
        {bracket ? `≥ Bracket ${bracket.floor}` : "≥ Bracket —"}
      </span>
      <span className="sr-only">at least. {FLOOR_COPY}</span>
      <span className="text-zinc-500">·</span>
      {!bracket ? (
        <span className="truncate text-[11px] text-zinc-400">run an analysis to see flags</span>
      ) : flags.length === 0 ? (
        <span className="truncate text-[11px] text-zinc-400">no flags found</span>
      ) : (
        <>
          {shown.map((f) => (
            <button
              key={f}
              type="button"
              onClick={onFlagClick ? () => onFlagClick(f) : undefined}
              title={f}
              className={[
                "inline-flex h-[18px] items-center rounded border border-magenta/60 bg-magenta/10 px-1.5 text-[11px] font-semibold text-[#ff9de9] hover:bg-magenta/20 focus-visible:outline focus-visible:outline-1 focus-visible:outline-cyan",
                compact ? "min-w-[48px] max-w-[180px] shrink" : "shrink-0",
              ].join(" ")}
            >
              <span className="truncate">{f}</span>
            </button>
          ))}
          {hidden > 0 && (
            <span className="shrink-0 text-[11px] text-zinc-400" aria-label={`${hidden} more flags: ${flags.slice(2).join(", ")}`}>
              +{hidden}
            </span>
          )}
        </>
      )}
    </div>
  );
}
