"use client";

export interface CountPillProps {
  count: number;
  target?: number;
  onOpenCuts: (n: number) => void;
  onOpenComplete: () => void;
}

/**
 * The single most prominent element on the board (§4.2):
 *   87 / 100 · 13 to add → Complete   (gold)
 *   100 / 100 ✓                        (cyan)
 *   103 / 100 · 3 over → Cut to 100    (gold)
 */
export function CountPill({ count, target = 100, onOpenCuts, onOpenComplete }: CountPillProps) {
  const diff = count - target;
  const state = diff === 0 ? "at" : diff > 0 ? "over" : "under";
  const tone =
    state === "at"
      ? "border-cyan/60 bg-cyan/10 text-cyan"
      : "border-accent/60 bg-accent/10 text-accent hover:bg-accent/20";
  const onClick = state === "over" ? () => onOpenCuts(diff) : state === "under" ? onOpenComplete : undefined;
  return (
    <button
      type="button"
      data-testid="count-pill"
      data-state={state}
      onClick={onClick}
      disabled={!onClick}
      className={`inline-flex h-10 items-center gap-2 rounded-md border px-3 text-[13px] font-semibold tabular-nums ${tone} disabled:cursor-default`}
    >
      <span className="text-[20px] leading-[22px]">{count}</span>
      <span className="text-[13px] opacity-80">/ {target}</span>
      {state === "at" && <span aria-label="complete">✓</span>}
      {state === "under" && (
        <>
          <span className="opacity-60">·</span>
          <span>{-diff} to add</span>
          <span className="opacity-60">→</span>
          <span className="underline decoration-accent/50 underline-offset-2">Complete</span>
        </>
      )}
      {state === "over" && (
        <>
          <span className="opacity-60">·</span>
          <span>{diff} over</span>
          <span className="opacity-60">→</span>
          <span className="underline decoration-accent/50 underline-offset-2">Cut to {target}</span>
        </>
      )}
    </button>
  );
}
