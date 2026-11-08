/**
 * Display formatting for a reason/signal value. Backend floats arrive with IEEE
 * noise ("0.15000000000000002", "0.7100000000000001"); chips and evidence rows
 * show at most 2 decimals, trailing zeros trimmed ("0.15", "0.71", "1", "-0.15").
 * Non-finite values render as "" (nothing is invented).
 */
export function formatSignal(value: number | null | undefined, decimals = 2): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "";
  const rounded = Number(value.toFixed(decimals));
  // Avoid "-0" after rounding tiny negatives.
  return String(Object.is(rounded, -0) ? 0 : rounded);
}
