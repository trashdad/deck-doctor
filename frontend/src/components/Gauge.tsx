"use client";

// DeckCheck-style radial gauge. value in [0, max].
export function Gauge({
  label,
  value,
  max,
  suffix = "",
}: {
  label: string;
  value: number;
  max: number;
  suffix?: string;
}) {
  const pct = Math.max(0, Math.min(1, value / max));
  const r = 34;
  const c = 2 * Math.PI * r;
  const dash = c * pct;
  const hue = 120 * pct; // red -> green
  return (
    <div className="flex flex-col items-center">
      <svg width="92" height="92" viewBox="0 0 92 92" className="-rotate-90">
        <circle cx="46" cy="46" r={r} fill="none" stroke="#2a2540" strokeWidth="9" />
        <circle
          cx="46"
          cy="46"
          r={r}
          fill="none"
          stroke={`hsl(${hue} 70% 55%)`}
          strokeWidth="9"
          strokeLinecap="round"
          strokeDasharray={`${dash} ${c}`}
        />
      </svg>
      <div className="-mt-[62px] flex h-[44px] flex-col items-center justify-center">
        <span className="text-lg font-bold text-zinc-100">
          {value}
          <span className="text-xs text-zinc-400">{suffix}</span>
        </span>
      </div>
      <span className="mt-3 text-[11px] uppercase tracking-wide text-zinc-400">
        {label}
      </span>
    </div>
  );
}
