/*
 * live-real-tabs.spec.ts — Suggest / Combos / Tune-up rail tabs and the < 1024 px bottom sheet,
 * against the REAL backend (:8001) and real card data. No page.route anywhere.
 * Needs: backend on :8001 (DATABASE_URL set); Playwright starts `npm run dev` on :3000.
 *
 * The deck is built through the real API in beforeAll exactly as live-real.spec.ts does
 * (Wayta + /deck/complete + 6 extra picks), and every assertion compares what the page shows
 * with the response the page itself received (page.waitForResponse), so a backend contract or
 * data change, or a UI that drops/reorders backend content, fails here.
 *
 * Projects: live-real-tabs-desktop (1440x900) runs the desktop-rail tests;
 *           live-real-tabs-mobile (iPhone 13 geometry, Chromium) runs the bottom-sheet tests.
 */
import { test, expect, type Page, type Response } from "@playwright/test";

const API = "http://localhost:8001";
const SLOW = 60_000;
test.describe.configure({ timeout: 120_000 });
const LAND = (t: string) => t.toLowerCase().includes("land");
const BASIC = /^(Plains|Island|Swamp|Mountain|Forest)$/;

type AnyCard = { id: string; name: string; color_identity?: string[]; type_line: string };
let deckState: { state: { cards: Record<string, { card: AnyCard; zone: string }>; basics: Record<string, { card: AnyCard; quantity: number }> }; version: 0 };
let commander: AnyCard;
let totalCards = 0;

async function j(path: string, init?: RequestInit) {
  const r = await fetch(API + path, init);
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json();
}
const post = (p: string, b: unknown) =>
  j(p, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) });

test.beforeAll(async () => {
  test.setTimeout(90_000);
  const cmd = (await j("/cards/commanders?q=Wayta&limit=1"))[0];
  commander = cmd;
  const comp = await post("/deck/complete", { commander_id: cmd.id, cards: [] });
  const cards: Record<string, { card: any; zone: string }> = { [cmd.id]: { card: cmd, zone: "Commanders" } };
  const basics: Record<string, { card: any; quantity: number }> = {};
  const put = (card: any, zone: string, qty: number) => {
    if (BASIC.test(card.name)) basics[card.id] = { card, quantity: (basics[card.id]?.quantity ?? 0) + qty };
    else cards[card.id] = { card, zone };
  };
  for (const a of comp.added) put(a.card, a.zone, a.quantity);
  const extra = (await j(`/cards?commander_id=${cmd.id}&limit=60`))
    .filter((c: any) => !cards[c.id] && !LAND(c.type_line))
    .slice(0, 6);
  for (const c of extra) put(c, "Utility", 1);
  totalCards = Object.keys(cards).length + Object.values(basics).reduce((n, b) => n + b.quantity, 0);
  deckState = { state: { cards, basics }, version: 0 };
});

async function open(page: Page) {
  await page.addInitScript((payload) => {
    window.localStorage.setItem("simmander.deck", payload);
    window.localStorage.setItem("dd-workbench", "1");
  }, JSON.stringify(deckState));
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error" || /same key|unique "key"/.test(m.text())) errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
  const bad: string[] = [];
  page.on("response", (r) => { if (r.url().includes("/api/") && r.status() >= 400) bad.push(`${r.status()} ${r.url()}`); });
  return { errors, bad };
}

/** Live deck from the persisted store (what the app itself would reload). */
const deckNow = (page: Page) =>
  page.evaluate(() => {
    const s = JSON.parse(localStorage.getItem("simmander.deck")!).state;
    const count = Object.keys(s.cards).length + Object.values<any>(s.basics).reduce((n, b) => n + b.quantity, 0);
    const zones: Record<string, string> = {};
    for (const [id, dc] of Object.entries<any>(s.cards)) zones[id] = dc.zone;
    return { count, ids: Object.keys(s.cards), zones };
  });
const count = async (page: Page) => (await deckNow(page)).count;

const respTo = (page: Page, re: RegExp) =>
  page.waitForResponse((r: Response) => re.test(r.url()) && r.request().method() === "POST" && r.status() === 200, { timeout: SLOW });

const subset = (a: string[] | undefined, b: string[] | undefined) => (a ?? []).every((c) => (b ?? []).includes(c));
const staplesOnly = (s: any) => s.reasons.length > 0 && s.reasons.every((r: any) => r.signal === "staple");
const isDesktopProject = () => !test.info().project.name.includes("mobile");
const tabs = (page: Page) => page.locator(isDesktopProject() ? '[data-testid="rail-tabs"]' : '[data-testid="rail-tabbar"]');

/** Suggest rows must be exactly the response's suggestions minus staple-only and in-deck cards, in order. */
async function assertSuggestMatches(page: Page, body: any) {
  const inDeck = new Set(Object.keys(deckState.state.cards));
  const expected = body.suggestions.filter((s: any) => !staplesOnly(s) && !inDeck.has(s.card.id));
  expect(expected.length, "backend returned something to show").toBeGreaterThan(0);
  const rows = page.getByTestId("suggest-panel").getByTestId("rail-row");
  await expect(rows).toHaveCount(expected.length, { timeout: SLOW });
  expect(await rows.evaluateAll((els) => els.map((e) => e.getAttribute("data-card-id")))).toEqual(expected.map((s: any) => s.card.id));
  return { rows, expected };
}

/* ------------------------------------------------------------------ desktop rail ------------------------------------------------------------------ */

test.describe("desktop rail", () => {
  test.beforeEach(() => test.skip(!isDesktopProject(), "desktop rail"));

  test("Suggest rows carry the backend's reasons; + adds exactly one card; Undo restores", async ({ page }) => {
    const { errors, bad } = await open(page);
    const recResp = respTo(page, /\/deck\/recommend\?/);
    await page.goto("/deck-doctor?workbench=1");
    const recRes = await recResp;
    expect(recRes.url()).toContain("explain=true");
    const body = await recRes.json();
    await expect(tabs(page).locator('[data-tab="suggest"]')).toHaveAttribute("aria-selected", "true");
    const panel = page.getByTestId("suggest-panel");
    // Source line names the tier the backend reported.
    const TIER: Record<string, string> = { edhrec: "EDHREC · real decks", cooccurrence: "real decks · mechanics", color_staple: "generic staples" };
    await expect(panel).toContainText(TIER[body.tier]);
    const { rows, expected } = await assertSuggestMatches(page, body);

    // Every row: name from the response; every chip's tooltip is one of that card's backend `detail`s;
    // the row's evidence list (why ▾) prints each backend detail verbatim.
    const n = Math.min(await rows.count(), 8);
    for (let i = 0; i < n; i++) {
      const s = expected[i];
      const row = rows.nth(i);
      await expect(row.locator("p.truncate")).toHaveText(s.card.name);
      expect(s.reasons.length, `${s.card.name} has reasons`).toBeGreaterThan(0);
      const details = s.reasons.map((r: any) => r.detail);
      const chipTitles = await row.locator("[data-reason-chip]").evaluateAll((els) => els.map((e) => e.getAttribute("title")));
      expect(chipTitles.length).toBeGreaterThan(0);
      for (const t of chipTitles) expect(details).toContain(t);
      await expect(row.locator("[data-reason-sentence]")).not.toHaveText("No evidence returned for this card.");
      await row.getByRole("button", { name: /why/i }).click();
      const ev = row.locator("[data-reason-evidence] li");
      await expect(ev).toHaveCount(s.reasons.length);
      for (const d of details) await expect(row.locator("[data-reason-evidence]")).toContainText(d);
    }

    // + on the first row: exactly +1, the card lands in the deck, the row disappears, Undo puts it back.
    const pick = expected[0];
    const before = await deckNow(page);
    expect(before.count).toBe(totalCards);
    await rows.first().getByRole("button", { name: `Add to deck: ${pick.card.name}` }).click();
    await expect.poll(() => count(page)).toBe(totalCards + 1);
    expect((await deckNow(page)).ids).toContain(pick.card.id);
    await expect(page.getByTestId("count-pill")).toContainText(String(totalCards + 1));
    await expect(panel.locator(`[data-card-id="${pick.card.id}"]`)).toHaveCount(0);
    await page.getByRole("button", { name: "Undo", exact: true }).click({ timeout: 10_000 });
    await expect.poll(() => count(page)).toBe(totalCards);
    expect((await deckNow(page)).ids).not.toContain(pick.card.id);
    expect(errors, errors.join("\n")).toEqual([]);
    expect(bad, bad.join("\n")).toEqual([]);
  });

  test("Suggest respects color identity: every row is inside Wayta's identity and a multicolor pick lands", async ({ page }) => {
    const { errors } = await open(page);
    const recResp = respTo(page, /\/deck\/recommend\?/);
    await page.goto("/deck-doctor?workbench=1");
    const body = await recResp.then((r) => r.json());
    const ci = commander.color_identity ?? [];
    expect(ci.length, "commander identity").toBeGreaterThan(0);
    const offColor = body.suggestions.filter((s: any) => !subset(s.card.color_identity, ci)).map((s: any) => s.card.name);
    expect(offColor, "suggestions outside the commander's identity").toEqual([]);
    const { rows, expected } = await assertSuggestMatches(page, body);
    // The widest-identity row shown (exercises the store's subset gate with >1 colour).
    const idx = expected.reduce((best: number, s: any, i: number) => ((s.card.color_identity?.length ?? 0) > (expected[best].card.color_identity?.length ?? 0) ? i : best), 0);
    const pick = expected[idx];
    expect(pick.card.color_identity.length, "a multicolor suggestion exists").toBeGreaterThan(1);
    await rows.nth(idx).getByRole("button", { name: `Add to deck: ${pick.card.name}` }).click();
    await expect.poll(() => count(page)).toBe(totalCards + 1);
    const after = await deckNow(page);
    expect(after.ids).toContain(pick.card.id);
    // Every non-commander card now in the deck is still inside the identity.
    const deckCards = await page.evaluate(() => Object.values<any>(JSON.parse(localStorage.getItem("simmander.deck")!).state.cards).map((dc) => dc.card));
    const outside = deckCards.filter((c: any) => !subset(c.color_identity, ci)).map((c: any) => c.name);
    expect(outside).toEqual([]);
    expect(errors, errors.join("\n")).toEqual([]);
  });

  test("Combos tab lists the real Spellbook combos for the seeded deck; + Add completes one", async ({ page }) => {
    const { errors, bad } = await open(page);
    await page.goto("/deck-doctor?workbench=1");
    await expect(page.getByTestId("workbench-live")).toBeVisible({ timeout: SLOW });
    const comboResp = respTo(page, /\/deck\/combos$/);
    await tabs(page).locator('[data-tab="combos"]').click();
    const res = await comboResp;
    const sent = res.request().postDataJSON();
    expect(sent.commander_id).toBe(commander.id);
    expect(new Set(sent.cards.map((c: any) => c.id))).toEqual(
      new Set([...Object.keys(deckState.state.cards), ...Object.keys(deckState.state.basics)]),
    );
    const body = await res.json();
    const complete = body.complete ?? [];
    const near = body.near ?? [];
    expect(complete.length + near.length, "Spellbook found combos for this deck").toBeGreaterThan(0);
    const panel = page.getByTestId("combos-panel");
    await expect(panel).toContainText(`In your deck (${complete.length})`, { timeout: SLOW });
    await expect(panel).toContainText(`One card away (${near.length})`);
    await expect(panel).toContainText(`${complete.length} complete · ${near.length} one-away · Commander Spellbook`);

    // Complete combos: every member really is in the seeded deck; the cards render produces + members.
    const inDeck = new Set([...Object.keys(deckState.state.cards), ...Object.keys(deckState.state.basics)]);
    const notInDeck = complete.flatMap((c: any) => c.members.filter((m: any) => !inDeck.has(m.id)).map((m: any) => `${c.combo_id}:${m.name}`));
    expect(notInDeck, "complete-combo members missing from the deck").toEqual([]);
    const cBoxes = page.getByTestId("combos-complete").locator(":scope > div");
    await expect(cBoxes).toHaveCount(complete.length);
    for (let i = 0; i < Math.min(complete.length, 10); i++) {
      const c = complete[i];
      if (c.produces.length) await expect(cBoxes.nth(i)).toContainText(`→ ${c.produces.join(", ")}`);
      expect(await cBoxes.nth(i).locator("button").allTextContents()).toEqual(c.members.map((m: any) => m.name));
    }

    // Near combos: "add X" names the response's missing card, which is not in the deck and is in identity.
    const ci = commander.color_identity ?? [];
    const nBoxes = page.getByTestId("combos-near").locator(":scope > div");
    await expect(nBoxes).toHaveCount(near.length);
    for (let i = 0; i < near.length; i++) {
      const n = near[i];
      expect(inDeck.has(n.missing.id), `${n.missing.name} should be missing`).toBe(false);
      expect(subset(n.missing.color_identity, ci), `${n.missing.name} inside identity`).toBe(true);
      if (i < 10) await expect(nBoxes.nth(i)).toContainText(`add ${n.missing.name}`);
    }

    // + Add on the first near combo: +1 card, and the refetched /deck/combos now lists that combo as complete.
    if (near.length > 0) {
      const n0 = near[0];
      const refetch = page.waitForResponse(
        (r) => /\/deck\/combos$/.test(r.url()) && r.status() === 200 && (r.request().postDataJSON()?.cards ?? []).some((c: any) => c.id === n0.missing.id),
        { timeout: SLOW },
      );
      await nBoxes.first().getByRole("button", { name: "+ Add" }).click();
      await expect.poll(() => count(page)).toBe(totalCards + 1);
      expect((await deckNow(page)).ids).toContain(n0.missing.id);
      const after = await (await refetch).json();
      expect(after.complete.map((c: any) => c.combo_id)).toContain(n0.combo.combo_id);
      await expect(panel).toContainText(`In your deck (${after.complete.length})`, { timeout: SLOW });
    }
    expect(errors, errors.join("\n")).toEqual([]);
    expect(bad, bad.join("\n")).toEqual([]);
  });

  test("Tune-up renders the real upgrade-sweep swaps; Swap replaces the weak card in its lane", async ({ page }) => {
    const { errors, bad } = await open(page);
    await page.goto("/deck-doctor?workbench=1");
    await expect(page.getByTestId("workbench-live")).toBeVisible({ timeout: SLOW });
    const sweepResp = respTo(page, /\/deck\/upgrade-sweep\?/);
    await tabs(page).locator('[data-tab="tuneup"]').click();
    const res = await sweepResp;
    const url = new URL(res.url());
    expect(url.searchParams.get("weak")).toBe("16");
    expect(res.request().postDataJSON().commander_id).toBe(commander.id);
    const body = await res.json();
    const inDeck = new Set(Object.keys(deckState.state.cards));
    const swaps = (body.swaps ?? []).filter((s: any) => inDeck.has(s.target.id));
    expect(swaps.length, "sweep found weak cards").toBeGreaterThan(0);
    const panel = page.getByTestId("tuneup-panel");
    const items = panel.getByTestId("sweep-swap");
    await expect(items).toHaveCount(swaps.length, { timeout: SLOW });
    await expect(panel).toContainText(`${swaps.length} weak cards`);
    for (let i = 0; i < swaps.length; i++) {
      const s = swaps[i];
      const item = items.nth(i);
      await expect(item.locator("p.line-through")).toHaveText(s.target.name);
      // Weakness chips: tooltip = the backend's own detail strings (first two).
      const wTitles = await item.locator(":scope > div").first().locator("span[title]").evaluateAll((els) => els.map((e) => e.getAttribute("title")));
      expect(wTitles).toEqual(s.weakness_reasons.slice(0, 2).map((r: any) => r.detail));
      // Options in backend order.
      const optNames = await item.locator("ul > li p.truncate").allTextContents();
      expect(optNames).toEqual(s.options.map((o: any) => o.card.name));
    }

    // Controls present / missing (documented in the report, not asserted as product requirements).
    const missing: string[] = [];
    if ((await panel.getByTestId("sweep-slider").count()) === 0) missing.push("efficiency slider (sweep-slider)");
    if ((await panel.getByText(/favor commander synergy/i).count()) === 0) missing.push("Favor commander synergy toggle");
    if ((await panel.getByRole("button", { name: /run tune-up/i }).count()) === 0) missing.push("Run Tune-up button");
    test.info().annotations.push({ type: "tuneup-missing-controls", description: missing.join("; ") || "none" });

    // Swap the first option of the first swap: count unchanged, target out, replacement in the target's lane.
    const s0 = swaps.find((s: any) => s.options.length > 0 && !inDeck.has(s.options[0].card.id));
    expect(s0, "a swap with an option").toBeTruthy();
    const i0 = swaps.indexOf(s0);
    const zone = deckState.state.cards[s0.target.id].zone;
    await items.nth(i0).getByTestId("sweep-apply").first().click();
    await expect.poll(async () => (await deckNow(page)).ids.includes(s0.options[0].card.id)).toBe(true);
    const after = await deckNow(page);
    expect(after.count).toBe(totalCards);
    expect(after.ids).not.toContain(s0.target.id);
    expect(after.zones[s0.options[0].card.id]).toBe(zone);
    const undoBtn = page.getByRole("button", { name: "Undo", exact: true });
    test.info().annotations.push({ type: "tuneup-swap-undo-toast", description: (await undoBtn.count()) > 0 ? "present" : "absent" });
    expect(errors, errors.join("\n")).toEqual([]);
    expect(bad, bad.join("\n")).toEqual([]);
  });
});

/* ------------------------------------------------------------------ mobile sheet ------------------------------------------------------------------ */

const noHOverflow = async (page: Page, where: string) => {
  const m = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(m.sw, `horizontal overflow at ${where} (${m.sw} > ${m.iw})`).toBeLessThanOrEqual(m.iw);
};
const MIN_TOUCH = 44;

test.describe("mobile bottom sheet", () => {
  test.beforeEach(() => test.skip(isDesktopProject(), "mobile sheet"));

  test("tab bar opens the sheet on the tapped tab, switching tabs swaps the body, same tab closes", async ({ page }) => {
    const { errors, bad } = await open(page);
    const recResp = respTo(page, /\/deck\/recommend\?/);
    await page.goto("/deck-doctor?workbench=1");
    const vp = page.viewportSize()!;
    expect(vp.width).toBeLessThan(1024);
    const bar = page.getByTestId("rail-tabbar");
    await expect(bar).toBeVisible({ timeout: SLOW });
    await expect(page.getByTestId("rail-sheet")).toHaveCount(0);
    await expect(page.getByTestId("rail-tabs")).toHaveCount(0);
    const barBox = (await bar.boundingBox())!;
    expect(barBox.y + barBox.height).toBeGreaterThanOrEqual(vp.height - 1);
    for (const t of await bar.getByRole("tab").all()) {
      const b = (await t.boundingBox())!;
      expect(b.height, `tab ${await t.textContent()} height`).toBeGreaterThanOrEqual(MIN_TOUCH);
    }
    await noHOverflow(page, "board");

    // Cuts first: sheet opens on Cuts with the real to_100 overage.
    const cutsResp = respTo(page, /\/deck\/cuts\?.*to_100=true/);
    await bar.locator('[data-tab="cuts"]').tap();
    const sheet = page.getByTestId("rail-sheet");
    await expect(sheet).toBeVisible();
    const cutsBody = await (await cutsResp).json();
    await expect(sheet.getByTestId("cuts-over-by")).toHaveText(`${totalCards - 100} over`, { timeout: SLOW });
    expect(cutsBody.cuts.length).toBe(totalCards - 100);
    await expect(sheet.getByTestId("cuts-panel").getByTestId("rail-row")).toHaveCount(cutsBody.cuts.length);
    const sheetBox = (await sheet.boundingBox())!;
    expect(sheetBox.y + sheetBox.height).toBeLessThanOrEqual(barBox.y + 1);
    await noHOverflow(page, "cuts sheet");

    // Switch to Pivot inside the open sheet.
    await bar.locator('[data-tab="pivot"]').tap();
    await expect(sheet.getByTestId("pivot-panel")).toBeVisible();
    await expect(sheet.getByTestId("cuts-panel")).toHaveCount(0);
    await expect(sheet.getByTestId("pivot-panel")).toContainText(/No candidate beats|pivot/i, { timeout: SLOW });
    await noHOverflow(page, "pivot sheet");

    // Suggest: rows are the real /deck/recommend suggestions.
    await bar.locator('[data-tab="suggest"]').tap();
    await expect(sheet.getByTestId("suggest-panel")).toBeVisible();
    await assertSuggestMatches(page, await (await recResp).json());
    await noHOverflow(page, "suggest sheet");

    // Same tab again closes.
    await bar.locator('[data-tab="suggest"]').tap();
    await expect(page.getByTestId("rail-sheet")).toHaveCount(0);
    expect(errors, errors.join("\n")).toEqual([]);
    expect(bad, bad.join("\n")).toEqual([]);
  });

  test("Cuts in the sheet: Cut all is reachable and brings the deck to 100, Undo restores; 44 px targets", async ({ page }) => {
    const { errors } = await open(page);
    await page.goto("/deck-doctor?workbench=1");
    await page.getByTestId("rail-tabbar").locator('[data-tab="cuts"]').tap();
    const sheet = page.getByTestId("rail-sheet");
    const all = sheet.getByTestId("cuts-all");
    await expect(all).toBeEnabled({ timeout: SLOW });
    await expect(all).toHaveText(`Cut all ${totalCards - 100}`);
    await expect(all).toBeInViewport({ ratio: 1 });
    const sb = (await sheet.boundingBox())!;
    const ab = (await all.boundingBox())!;
    expect(ab.x).toBeGreaterThanOrEqual(sb.x);
    expect(ab.x + ab.width).toBeLessThanOrEqual(sb.x + sb.width + 1);
    expect(ab.y + ab.height).toBeLessThanOrEqual(sb.y + sb.height);
    // Touch targets (soft: the functional path below still runs and reports).
    expect.soft(ab.height, "Cut all button height").toBeGreaterThanOrEqual(MIN_TOUCH);
    const cutBtns = sheet.getByTestId("rail-row").getByRole("button", { name: /^Cut from deck/ });
    await expect(cutBtns.first()).toBeVisible();
    const cb = (await cutBtns.first().boundingBox())!;
    expect.soft(cb.height, "row Cut button height").toBeGreaterThanOrEqual(MIN_TOUCH);
    expect.soft(cb.width, "row Cut button width").toBeGreaterThanOrEqual(MIN_TOUCH);
    await noHOverflow(page, "cuts sheet");

    await all.tap();
    await expect.poll(() => count(page)).toBe(100);
    await expect(page.getByTestId("count-pill")).toHaveAttribute("data-state", "at");
    const undo = page.getByRole("button", { name: "Undo", exact: true });
    await expect(undo).toBeVisible();
    await expect(undo).toBeInViewport({ ratio: 1 });
    const ub = (await undo.boundingBox())!;
    expect.soft(ub.height, "toast Undo height").toBeGreaterThanOrEqual(MIN_TOUCH);
    await undo.tap();
    await expect.poll(() => count(page)).toBe(totalCards);
    await noHOverflow(page, "after undo");
    expect(errors, errors.join("\n")).toEqual([]);
  });

  test("Suggest in the sheet: backend reasons shown, + adds one card, targets are 44 px, no overflow", async ({ page }) => {
    const { errors } = await open(page);
    const recResp = respTo(page, /\/deck\/recommend\?/);
    await page.goto("/deck-doctor?workbench=1");
    await page.getByTestId("rail-tabbar").locator('[data-tab="suggest"]').tap();
    const sheet = page.getByTestId("rail-sheet");
    await expect(sheet.getByTestId("suggest-panel")).toBeVisible();
    const { rows, expected } = await assertSuggestMatches(page, await (await recResp).json());
    const details = expected[0].reasons.map((r: any) => r.detail);
    for (const t of await rows.first().locator("[data-reason-chip]").evaluateAll((els) => els.map((e) => e.getAttribute("title"))))
      expect(details).toContain(t);
    const plus = rows.first().getByRole("button", { name: `Add to deck: ${expected[0].card.name}` });
    const pb = (await plus.boundingBox())!;
    expect.soft(pb.height, "+ button height").toBeGreaterThanOrEqual(MIN_TOUCH);
    expect.soft(pb.width, "+ button width").toBeGreaterThanOrEqual(MIN_TOUCH);
    await noHOverflow(page, "suggest sheet");
    await plus.tap();
    await expect.poll(() => count(page)).toBe(totalCards + 1);
    expect((await deckNow(page)).ids).toContain(expected[0].card.id);
    await expect(sheet.locator(`[data-card-id="${expected[0].card.id}"]`)).toHaveCount(0);
    await noHOverflow(page, "after add");
    expect(errors, errors.join("\n")).toEqual([]);
  });
});
