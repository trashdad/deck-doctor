/**
 * FIXTURES + backend mock for tests/live-mock.spec.ts.
 *
 * The live Next app (`/deck-doctor`) is driven with EVERY backend call intercepted by
 * Playwright `page.route`, so no FastAPI on :8001 is needed. Responses are built from
 * `cards.json` next to this file — real cards copied by id from `data/cards.json`
 * (Scryfall ids / names / oracle text / image URLs). Nothing is invented; the ONLY
 * fixture annotations are `mechanic_tags` / `wincon` (lane placement) and the numeric
 * scores / reason sentences below, which are labelled "fixture" where they are visible.
 *
 * API base: lib/api.ts → `${BASE_PATH}/api` = `/deck-doctor/api` (dev rewrite to :8001).
 * Endpoints mocked (all the page + WorkbenchLive hit on load / per tab):
 *   GET  /auth/me, /templates, /decks, /cards?…, /cards/commanders
 *   POST /deck/analyze, /deck/diagnose, /deck/recommend, /deck/cuts (limit and
 *        ?to_100=true&target=N), /deck/combos, /deck/upgrade-sweep, /deck/pivot
 * Scores and reason sentences below are labelled "fixture". Card ids/names are real.
 * Anything else answers 404 JSON and is recorded in `calls.unexpected`.
 *
 * Deck persistence: store/deck.ts wraps the zustand store in `persist` under the
 * localStorage key "simmander.deck" with `partialize: { cards, basics }` → the stored
 * value is `{"state":{"cards":{id:{card,zone}},"basics":{id:{card,quantity}}},"version":0}`.
 * `seedDeckStorage` writes that before the app boots (addInitScript).
 *
 * Regenerate cards.json: load data/cards.json, pick the names listed in the deck / find /
 * reserve groups, copy id/name/cmc/type_line/oracle_text/colors/color_identity/power/
 * toughness/keywords/image_uris.normal, set ier=null and the fixture mechanic_tags.
 */
import type { Page, Route } from "@playwright/test";
import fx from "./cards.json";

export interface Card {
  id: string;
  name: string;
  cmc: number;
  type_line: string;
  oracle_text: string;
  colors: string[];
  color_identity: string[];
  power: string | null;
  toughness: string | null;
  keywords: string[];
  image_uris: { normal: string };
  ier: number | null;
  mechanic_tags: string[];
  wincon?: boolean;
}

export const FX = fx as unknown as {
  _fixture: string;
  commander: Card;
  deck: Card[];
  basic: Card;
  basicQuantity: number;
  find: Card[];
  reserve: Card[];
  /** Real commanders copied from data/cards.json. Not part of the seeded deck. */
  pivotCommanders: Card[];
};

export const API_PREFIX = "/deck-doctor/api";

/** Zone a card lands in — mirrors lib/functions.ts matchingZones + store/deck.ts add(). */
export function zoneFor(card: Card): string {
  if (card.wincon) return "Win Conditions";
  const t = card.type_line.toLowerCase();
  const tags = card.mechanic_tags;
  if (t.includes("land")) return "Lands";
  if (tags.includes("board_wipe")) return "Board Wipes";
  if (tags.includes("removal")) return "Removal";
  if (tags.includes("ramp")) return "Ramp";
  if (tags.includes("card_draw")) return "Card Draw";
  if (tags.some((x) => x.startsWith("counter_"))) return "Counters";
  if (tags.some((x) => x.startsWith("token_"))) return "Tokens";
  return "Utility";
}

/** The persisted deck-store payload (zustand/persist v4 envelope). */
export function seededDeckState() {
  const cards: Record<string, { card: Card; zone: string }> = {};
  cards[FX.commander.id] = { card: FX.commander, zone: "Commanders" };
  for (const c of FX.deck) cards[c.id] = { card: c, zone: zoneFor(c) };
  const basics = { [FX.basic.id]: { card: FX.basic, quantity: FX.basicQuantity } };
  return { state: { cards, basics }, version: 0 };
}

export const SEEDED_COUNT = 1 + FX.deck.length + FX.basicQuantity; // 103

/** Write the seeded deck into localStorage before any page script runs. */
export async function seedDeckStorage(page: Page, opts: { workbench?: boolean } = {}) {
  const payload = JSON.stringify(seededDeckState());
  await page.addInitScript(
    ({ payload, workbench }) => {
      try {
        window.localStorage.setItem("simmander.deck", payload);
        if (workbench) window.localStorage.setItem("dd-workbench", "1");
        else window.localStorage.removeItem("dd-workbench");
      } catch {
        /* ignore */
      }
    },
    { payload, workbench: !!opts.workbench },
  );
}

// ---------------------------------------------------------------- response builders

const reason = (signal: string, detail: string, value: number) => ({ signal, detail, value });

export function templatesResponse() {
  return {
    templates: [
      {
        id: "simmander_composite",
        name: "Simmander Composite",
        source: "fixture",
        counts: { land: 37, ramp: 10, card_draw: 9, removal: 8, board_wipe: 3 },
        notes: "fixture copy of the default composite counts (store/template.ts DEFAULT_COMPOSITE_COUNTS)",
      },
      {
        id: "command_zone",
        name: "Command Zone",
        source: "fixture",
        counts: { land: 38, ramp: 10, card_draw: 12, removal: 12, board_wipe: 3 },
        notes: "fixture",
      },
    ],
    themes: [],
  };
}

export function analyzeResponse(cardCount: number) {
  return {
    card_count: cardCount,
    mana_curve: [1, 2, 3, 4, 5, 6].map((cmc) => ({ cmc, count: FX.deck.filter((c) => Math.round(c.cmc) === cmc).length })),
    color_pips: { R: 70 },
    type_counts: { Creature: 14, Instant: 7, Sorcery: 6, Artifact: 7, Enchantment: 3, Land: 67 },
    efficiency: 6.1,
    impact: 5.4,
    average_playability: 71.2,
    score: 612,
    bracket: 3,
    bracket_reasons: ["fixture: 1 two-card infinite combo", "fixture: no mass land denial"],
    top_synergies: [],
    keepable_hand_pct: 84.0,
  };
}

export function diagnoseResponse() {
  return {
    score: 68,
    verdict: "FAIR",
    vitals: [
      { label: "Mana", score: 72 },
      { label: "Draw", score: 61 },
      { label: "Interaction", score: 66 },
      { label: "Synergy", score: 74 },
    ],
  };
}

export function recommendResponse() {
  const signals = ["edhrec", "cooccurrence", "synergy", "engine", "edhrec_inclusion"];
  return {
    tier: "edhrec",
    suggestions: FX.find.map((card, i) => ({
      card,
      score: Number((0.9 - i * 0.04).toFixed(3)),
      reasons: [
        reason(signals[i % signals.length], `fixture: ${card.name} with ${FX.commander.name}`, 0.8 - i * 0.03),
        reason("cooccurrence", "fixture: seen in corpus decks", 0.5),
      ],
    })),
  };
}

/** Cut candidates must be IN the deck (WorkbenchLive filters to `cards[id]`). */
export function cutsResponse(limit: number) {
  const weak = ["Wild Guess", "Tormenting Voice", "Cathartic Reunion", "Abrade", "Mind Stone"];
  const picks = weak.map((n) => FX.deck.find((c) => c.name === n)!).filter(Boolean).slice(0, limit);
  return {
    cuts: picks.map((card, i) => ({
      card,
      contribution: Number((0.05 + i * 0.02).toFixed(3)),
      reasons: [reason("edhrec", `fixture: low inclusion with ${FX.commander.name}`, 0.1 + i * 0.05), reason("synergy", "fixture: few deck synergies", 0.2)],
    })),
  };
}

export function combosResponse() {
  const byName = (n: string) => [...FX.deck, FX.commander, ...FX.find, ...FX.reserve].find((c) => c.name === n)!;
  const krenko = FX.commander;
  const staff = byName("Thornbite Staff");
  const prospector = byName("Skirk Prospector");
  const snoop = byName("Conspicuous Snoop"); // not in deck → "one card away"
  const recruiter = byName("Goblin Recruiter"); // not in deck
  return {
    complete: [
      {
        combo_id: "fixture-krenko-staff-prospector",
        identity: "R",
        popularity: null,
        description: "fixture: Krenko taps for Goblins; Skirk Prospector sacrifices one; Thornbite Staff untaps Krenko",
        produces: ["Infinite Goblin tokens", "Infinite red mana"],
        mana_needed: "{4}",
        members: [krenko, staff, prospector],
      },
    ],
    near: [
      {
        combo: {
          combo_id: "fixture-snoop-recruiter",
          identity: "R",
          popularity: null,
          description: "fixture: Goblin Recruiter stacks the library; Conspicuous Snoop casts Goblins off the top",
          produces: ["Infinite Goblin tokens"],
          mana_needed: "{5}",
          members: [snoop, recruiter, krenko],
        },
        missing: snoop,
      },
    ],
  };
}

export function sweepResponse() {
  const target = (n: string) => FX.deck.find((c) => c.name === n)!;
  const opt = (n: string) => [...FX.find, ...FX.reserve].find((c) => c.name === n)!;
  const mk = (t: Card, options: Card[], w: number) => ({
    target: t,
    weakness: w,
    weakness_reasons: [reason("edhrec", "fixture: low inclusion", w), reason("synergy", "fixture: little synergy", 0.2)],
    options: options.map((card, i) => ({
      card,
      score: 0.8 - i * 0.1,
      efficiency_gain: 1.2 - i * 0.4,
      similarity: 0.7,
      reasons: [reason("similar", "fixture: same role", 0.7), reason("synergy", `fixture: better with ${FX.commander.name}`, 0.6)],
    })),
  });
  return {
    swaps: [
      mk(target("Wild Guess"), [opt("Light Up the Stage"), opt("Jeska's Will")], 0.04),
      mk(target("Mind Stone"), [opt("Commander's Sphere")], 0.06),
      mk(target("Abrade"), [opt("Rakdos Charm"), opt("Deflecting Swat")], 0.08),
    ],
  };
}

function cardByName(name: string): Card {
  const all = [FX.commander, ...FX.deck, FX.basic, ...FX.find, ...FX.reserve, ...FX.pivotCommanders];
  const card = all.find((c) => c.name === name);
  if (!card) throw new Error(`live fixture has no card named ${name}`);
  return card;
}

/**
 * Role/curve-aware cuts. Numbers and sentences are FIXTURE data (labelled),
 * built on real cards that are in the seeded deck. The third row breaks quota.
 */
export function cutsTo100Response(target: number, postedCount: number) {
  const label: Record<string, string> = {
    land: "Lands",
    ramp: "Ramp",
    card_draw: "Card Draw",
    removal: "Removal",
    board_wipe: "Board Wipes",
    utility: "Utility",
  };
  const pool: {
    name: string;
    role: string;
    role_before: number;
    quota: number;
    breaks: boolean;
    bin: number;
    curve_before: number;
    curve_after: number;
    curve_ideal: number;
  }[] = [
    { name: "Wild Guess", role: "card_draw", role_before: 11, quota: 9, breaks: false, bin: 2, curve_before: 8, curve_after: 7, curve_ideal: 6.5 },
    { name: "Tormenting Voice", role: "card_draw", role_before: 10, quota: 9, breaks: false, bin: 2, curve_before: 7, curve_after: 6, curve_ideal: 6.5 },
    { name: "Sol Ring", role: "ramp", role_before: 10, quota: 10, breaks: true, bin: 1, curve_before: 6, curve_after: 5, curve_ideal: 4.2 },
    { name: "Cathartic Reunion", role: "card_draw", role_before: 9, quota: 9, breaks: false, bin: 2, curve_before: 6, curve_after: 5, curve_ideal: 6.5 },
  ];
  const n = Number.isFinite(target) ? Math.max(0, Math.min(30, Math.floor(target))) : 0;
  const cuts = pool.slice(0, n).map((spec, i) => {
    const card = cardByName(spec.name);
    const roleName = label[spec.role] ?? "UNKNOWN";
    const after = spec.role_before - 1;
    const roleTxt = spec.breaks
      ? `cutting it drops ${roleName} to ${after}, below the template's ${spec.quota} (nothing else is left to cut)`
      : `${roleName} ${spec.role_before} → ${after} stays at or above the template's ${spec.quota}`;
    const curveTxt = `cmc ${spec.bin}: that bin goes ${spec.curve_before} → ${spec.curve_after} (within the ideal ${spec.curve_ideal})`;
    return {
      card,
      contribution: Number((0.05 + i * 0.02).toFixed(3)),
      reasons: [
        reason("edhrec", `fixture: low inclusion with ${FX.commander.name}`, 0.1 + i * 0.05),
        reason("synergy", "fixture: few deck synergies", 0.2),
      ],
      role: spec.role,
      role_before: spec.role_before,
      role_after: after,
      quota: spec.quota,
      quota_after: after,
      curve_bin: spec.bin,
      curve_before: spec.curve_before,
      curve_after: spec.curve_after,
      curve_ideal: spec.curve_ideal,
      breaks_quota: spec.breaks,
      reason: `fixture: ${card.name}: low inclusion with ${FX.commander.name}; ${roleTxt}; ${curveTxt}.`,
    };
  });
  return {
    cuts,
    over_by: postedCount - 100,
    target: n,
    shortfall: Math.max(0, n - cuts.length),
  };
}

const PIVOT_OFF_COLOUR = [
  "Lightning Bolt",
  "Goblin Bombardment",
  "Skirk Prospector",
  "Goblin Warchief",
  "Goblin Matron",
  "Goblin Chieftain",
  "Krenko's Command",
  "Siege-Gang Commander",
];

function deckIdentity(): string[] {
  const present = new Set<string>();
  for (const card of FX.deck) for (const c of card.color_identity) present.add(c);
  return ["W", "U", "B", "R", "G"].filter((c) => present.has(c));
}

/** FIXTURE pivot scores — not a live EDHREC read. Card objects are real. */
export function pivotResponse(includeAll: boolean) {
  const deckSize = FX.deck.length;
  const offNames = PIVOT_OFF_COLOUR.map((name) => cardByName(name).name);
  const pct = (n: number) => `${Math.round(n * 100)}%`;
  const signed = (n: number) => `${n >= 0 ? "+" : ""}${n.toFixed(2)}`;

  const row = (
    name: string,
    partial: {
      hits: number;
      page_size: number;
      inclusion_mean: number;
      synergy_mean: number | null;
      off_color_count: number;
      score: number;
    },
    better: boolean,
  ) => {
    const metrics = { ...partial, coverage: Number((partial.hits / deckSize).toFixed(4)) };
    const card = cardByName(name);
    const ident = (card.color_identity ?? []).join("") || "colorless";
    const evidence: { signal: string; value: number; detail: string }[] = [
      {
        signal: "coverage",
        value: metrics.coverage,
        detail: `fixture: ${metrics.hits} of your ${deckSize} cards appear on ${card.name}'s EDHREC page (${metrics.page_size} cards listed)`,
      },
      {
        signal: "edhrec_inclusion",
        value: metrics.inclusion_mean,
        detail: `fixture: mean EDHREC inclusion across your deck ${pct(metrics.inclusion_mean)}`,
      },
    ];
    const clauses = [
      `${metrics.hits} of your ${deckSize} cards appear on ${card.name}'s EDHREC page`,
      `mean inclusion ${pct(metrics.inclusion_mean)}`,
    ];
    if (metrics.synergy_mean != null) {
      evidence.push({
        signal: "edhrec_synergy",
        value: metrics.synergy_mean,
        detail: `fixture: mean EDHREC synergy over those ${metrics.hits} cards ${signed(metrics.synergy_mean)}`,
      });
      clauses.push(`mean synergy ${signed(metrics.synergy_mean)}`);
    }
    let sentence = `fixture: ${clauses.join("; ")}.`;
    if (metrics.off_color_count > 0) {
      const more = metrics.off_color_count > offNames.length ? ` (+${metrics.off_color_count - offNames.length} more)` : "";
      const shown = offNames.join(", ");
      evidence.push({
        signal: "off_color",
        value: metrics.off_color_count,
        detail: `fixture: ${metrics.off_color_count} cards fall outside its ${ident} identity: ${shown}${more}`,
      });
      sentence += ` ${metrics.off_color_count} of your cards would have to go (outside ${ident}): ${shown}${more}.`;
    }
    return {
      commander: card,
      in_identity: metrics.off_color_count === 0,
      off_color_names: metrics.off_color_count === 0 ? [] : offNames,
      deck_count: 0,
      better_than_current: better,
      metrics,
      reason: sentence,
      evidence,
    };
  };

  const currentMetrics = {
    hits: 28,
    page_size: 100,
    coverage: Number((28 / deckSize).toFixed(4)),
    inclusion_mean: 0.35,
    synergy_mean: 0.2,
    off_color_count: 0,
    score: 0.41,
  };
  const candidates = [
    row("Muxus, Goblin Grandee", { hits: 30, page_size: 100, inclusion_mean: 0.4, synergy_mean: 0.22, off_color_count: 0, score: 0.62 }, true),
    row(
      "Meren of Clan Nel Toth",
      { hits: 8, page_size: 100, inclusion_mean: 0.06, synergy_mean: 0.02, off_color_count: 12, score: 0.48 },
      true,
    ),
  ];
  if (includeAll) {
    candidates.push(
      row(
        "Karador, Ghost Chieftain",
        { hits: 6, page_size: 100, inclusion_mean: 0.04, synergy_mean: 0.01, off_color_count: 12, score: 0.22 },
        false,
      ),
    );
  }
  return {
    deck_size: deckSize,
    deck_identity: deckIdentity(),
    current: { commander: FX.commander, metrics: currentMetrics },
    candidates,
  };
}

/** Same baseline as pivotResponse, with no candidate returned. */
export function pivotEmptyResponse() {
  return { ...pivotResponse(false), candidates: [] as unknown[] };
}

// ---------------------------------------------------------------- the router

export interface MockCalls {
  all: { method: string; path: string; search: string }[];
  unexpected: { method: string; path: string }[];
  /** paths hit, deduped, in order */
  paths(): string[];
}

export async function mockBackend(page: Page): Promise<MockCalls> {
  const calls: MockCalls = {
    all: [],
    unexpected: [],
    paths() {
      return [...new Set(this.all.map((c) => c.path))];
    },
  };
  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

  await page.route(`**${API_PREFIX}/**`, async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const path = url.pathname.slice(url.pathname.indexOf(API_PREFIX) + API_PREFIX.length);
    const method = req.method();
    calls.all.push({ method, path, search: url.search });

    if (method === "GET" && path === "/auth/me") return json(route, { user: null });
    if (method === "GET" && path === "/templates") return json(route, templatesResponse());
    if (method === "GET" && path === "/decks") return json(route, []);
    if (method === "GET" && path === "/cards/commanders") return json(route, [FX.commander]);
    if (method === "GET" && path === "/cards") {
      const q = (url.searchParams.get("q") ?? "").toLowerCase();
      return json(route, q ? FX.find.filter((c) => c.name.toLowerCase().includes(q)) : FX.find);
    }
    if (method === "POST") {
      const body = req.postDataJSON() as { cards?: { quantity: number }[] } | null;
      const n = body?.cards?.reduce((s, e) => s + (e.quantity ?? 1), 0) ?? SEEDED_COUNT;
      if (path === "/deck/analyze") return json(route, analyzeResponse(n));
      if (path === "/deck/diagnose") return json(route, diagnoseResponse());
      if (path === "/deck/recommend") return json(route, recommendResponse());
      if (path === "/deck/cuts") {
        if (url.searchParams.get("to_100") === "true") {
          return json(route, cutsTo100Response(Number(url.searchParams.get("target") ?? "1"), n));
        }
        return json(route, cutsResponse(Number(url.searchParams.get("limit") ?? 10)));
      }
      if (path === "/deck/pivot") return json(route, pivotResponse(url.searchParams.get("include_all") === "true"));
      if (path === "/deck/combos") return json(route, combosResponse());
      if (path === "/deck/upgrade-sweep") return json(route, sweepResponse());
    }
    calls.unexpected.push({ method, path });
    return json(route, { detail: `live-mock: no fixture for ${method} ${path}` }, 404);
  });

  // The tracker's shared auth lives at the site root; never let it leave the box.
  await page.route(/^https?:\/\/[^/]+\/api\/auth\//, (route) => json(route, { detail: "live-mock" }, 404));

  return calls;
}
