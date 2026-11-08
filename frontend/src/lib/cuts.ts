/**
 * Cut to 100 — POST /deck/cuts?to_100=true&target=N (backend/app/cut_to_100.py).
 *
 * `target` is how many cards to cut (route cap 1–30), not the deck size.
 * Every displayed number comes from the response. A missing field is omitted
 * or shown as UNKNOWN; nothing is filled in on the client.
 *
 * Kept in its own module (not api.ts) so the mode can land without touching
 * the shared client. BASE mirrors api.ts (path-hosted at /deck-doctor).
 */
import type { Card, Cut, DeckEntry, Reason } from "./types";
import type { Zone } from "./zones";

const BASE_PATH =
  process.env.NEXT_PUBLIC_BASE_PATH === ""
    ? ""
    : process.env.NEXT_PUBLIC_BASE_PATH || "/deck-doctor";
const BASE = `${BASE_PATH}/api`;

/** Route rejects target outside 1..30 (main.py Query ge=1, le=30). */
export const CUT_TARGET_MAX = 30;

export function clampCutTarget(n: number): number {
  if (!Number.isFinite(n)) return 1;
  return Math.min(CUT_TARGET_MAX, Math.max(1, Math.floor(n)));
}

/** Backend role key → the lane name cut_to_100._ROLE_LABEL uses. */
export const CUT_ROLE_ZONE: Record<string, Zone> = {
  land: "Lands",
  ramp: "Ramp",
  card_draw: "Card Draw",
  removal: "Removal",
  board_wipe: "Board Wipes",
  utility: "Utility",
};

export interface CutTo100 extends Cut {
  role: string | null;
  role_before: number | null;
  quota_after: number | null;
  quota: number | null;
  curve_bin: number | null;
  curve_before: number | null;
  curve_after: number | null;
  curve_ideal: number | null;
  breaks_quota: boolean | null;
  reason: string | null;
}

/** A default-mode Cut, or a to_100 cut. Extra fields are optional so old rows still type-check. */
export type CutRow = Cut & Partial<Omit<CutTo100, keyof Cut>>;

export interface CutsTo100Response {
  cuts: CutTo100[];
  over_by: number | null;
  target: number | null;
  shortfall: number | null;
}

export interface CutsTo100Options {
  /** Active template quotas (doctor keys). Omitted when the caller has none. */
  template?: Record<string, number> | null;
}

function finiteTemplate(template?: Record<string, number> | null): Record<string, number> | undefined {
  if (!template) return undefined;
  const out: Record<string, number> = {};
  for (const [key, value] of Object.entries(template)) {
    if (typeof value === "number" && Number.isFinite(value)) out[key] = value;
  }
  return Object.keys(out).length > 0 ? out : undefined;
}

/** Role/curve-aware cuts. `target` is clamped to the route's 1–30 cap before the request. */
export async function postCutsTo100(
  cards: DeckEntry[],
  commander_id: string,
  target: number,
  opts: CutsTo100Options = {},
): Promise<CutsTo100Response> {
  const qs = new URLSearchParams({
    to_100: "true",
    target: String(clampCutTarget(target)),
  });
  const template = finiteTemplate(opts.template);
  const res = await fetch(`${BASE}/deck/cuts?${qs.toString()}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      cards,
      commander_id,
      ...(template ? { template } : {}),
    }),
    credentials: "include",
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<CutsTo100Response>;
}

function num(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? String(value) : "UNKNOWN";
}

/**
 * "Card Draw 11 → 10" or "Ramp 10 → 9 (below quota 10)".
 * Returns undefined when the response carried no role/quota fields (default-mode cuts).
 */
export function cutQuotaNote(cut: CutRow): string | undefined {
  const has =
    cut.role != null ||
    cut.role_before != null ||
    cut.quota_after != null ||
    cut.quota != null ||
    cut.breaks_quota != null;
  if (!has) return undefined;
  const label = cut.role == null ? "UNKNOWN" : (CUT_ROLE_ZONE[cut.role] ?? "UNKNOWN");
  let text = `${label} ${num(cut.role_before)} → ${num(cut.quota_after)}`;
  if (cut.breaks_quota === true) text += ` (below quota ${num(cut.quota)})`;
  return text;
}

/** Lane for the role chip. undefined → caller may fall back; null → the role string was not a known key. */
export function cutRoleZone(role: string | null | undefined): Zone | null | undefined {
  if (role == null) return undefined;
  return CUT_ROLE_ZONE[role] ?? null;
}

/** The backend `reason` sentence. undefined → the field was absent (use ReasonLine). */
export function cutReasonSentence(cut: CutRow): string | undefined {
  if (!Object.prototype.hasOwnProperty.call(cut, "reason")) return undefined;
  const text = (cut.reason ?? "").trim();
  return text || "UNKNOWN";
}

export function cutReasons(cut: CutRow): Reason[] {
  return Array.isArray(cut.reasons) ? cut.reasons : [];
}
