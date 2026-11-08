/*
 * live-real.spec.ts — the workbench against the REAL backend (:8001) and the real card data.
 * No page.route. Needs: backend on :8001 (DATABASE_URL set), `npm run dev` on :3000.
 * The deck is built through the real API in beforeAll (Wayta + /deck/complete + 6 extra picks),
 * so a data or contract change on the backend breaks these tests, which the mocked suite cannot.
 */
import { test, expect, type Page } from "@playwright/test";

const API = "http://localhost:8001";
// Cold `next dev` + /api proxy can take a while when the whole suite runs in parallel.
const SLOW = 60_000;
test.describe.configure({ timeout: 90_000 });
const LAND = (t: string) => t.toLowerCase().includes("land");
const BASIC = /^(Plains|Island|Swamp|Mountain|Forest)$/;

let deckState: { state: { cards: Record<string, unknown>; basics: Record<string, unknown> }; version: 0 };
let commanderId = "";
let totalCards = 0;

async function j(path: string, init?: RequestInit) {
  const r = await fetch(API + path, init);
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json();
}
const post = (p: string, b: unknown) =>
  j(p, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) });

test.beforeAll(async () => {
  const cmd = (await j("/cards/commanders?q=Wayta&limit=1"))[0];
  commanderId = cmd.id;
  const comp = await post("/deck/complete", { commander_id: cmd.id, cards: [] });
  const cards: Record<string, { card: any; zone: string }> = {
    [cmd.id]: { card: cmd, zone: "Commanders" },
  };
  const basics: Record<string, { card: any; quantity: number }> = {};
  const put = (card: any, zone: string, qty: number) => {
    if (BASIC.test(card.name)) {
      basics[card.id] = { card, quantity: (basics[card.id]?.quantity ?? 0) + qty };
    } else cards[card.id] = { card, zone };
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
  await page.goto("/deck-doctor?workbench=1");
  return { errors, bad };
}

test("real deck is over 100 and Cuts tab shows real to_100 rows", async ({ page }) => {
  test.skip(test.info().project.name.includes("mobile"), "desktop rail");
  expect(totalCards, "seeded deck size").toBeGreaterThan(100);
  const { errors, bad } = await open(page);
  const cutsResp = page.waitForResponse((r) => /\/deck\/cuts\?.*to_100=true/.test(r.url()), { timeout: SLOW });
  await page.getByRole("tab", { name: /cuts/i }).click();
  const panel = page.getByTestId("cuts-panel");
  await expect(panel).toBeVisible();
  await expect(page.getByTestId("cuts-over-by")).toHaveText(`${totalCards - 100} over`, { timeout: SLOW });
  const body = await (await cutsResp).json();
  expect(body.cuts.length).toBe(totalCards - 100);
  const rows = panel.getByTestId("rail-row");
  await expect(rows).toHaveCount(totalCards - 100);
  // Every row names a card and carries a non-empty sentence from the backend.
  for (let i = 0; i < (await rows.count()); i++) {
    // The row must show the backend's own sentence, not a ReasonLine fallback.
    expect(typeof body.cuts[i].reason).toBe("string");
    expect(body.cuts[i].reason.trim().length).toBeGreaterThan(10);
    await expect(rows.nth(i).locator("[data-reason-sentence]")).toHaveText(body.cuts[i].reason.trim());
    await expect(rows.nth(i)).not.toContainText("UNKNOWN");
  }
  expect(errors, errors.join("\n")).toEqual([]);
  expect(bad, bad.join("\n")).toEqual([]);
});

test("Cut all brings the real deck to 100 and Undo restores it", async ({ page }) => {
  test.skip(test.info().project.name.includes("mobile"), "desktop rail");
  expect(totalCards, "seeded deck size").toBeGreaterThan(100);
  const { errors, bad } = await open(page);
  await page.getByRole("tab", { name: /cuts/i }).click();
  const all = page.getByTestId("cuts-all");
  await expect(all).toBeEnabled({ timeout: SLOW });
  // Which cards will go: the rows the tab shows (one per copy).
  const goingNames = await page.getByTestId("cuts-panel").getByTestId("rail-row").locator("p.truncate").allTextContents();
  await all.click();
  const count = () => page.evaluate(() => {
    const s = JSON.parse(localStorage.getItem("simmander.deck")!).state;
    return Object.keys(s.cards).length + Object.values<any>(s.basics).reduce((n, b) => n + b.quantity, 0);
  });
  await expect.poll(count).toBe(100);
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect.poll(count).toBe(totalCards);
  expect(errors, errors.join("\n")).toEqual([]);
});

test("Pivot tab lists real candidate commanders with sentences; menu has no Add to deck", async ({ page }) => {
  test.skip(test.info().project.name.includes("mobile"), "desktop rail");
  const { errors, bad } = await open(page);
  await page.getByRole("tab", { name: /pivot/i }).click();
  // Without "Include all" nothing beats this commander's own score, so the empty state names it.
  await expect(page.getByTestId("pivot-panel")).toContainText("No candidate beats", { timeout: SLOW });
  await expect(page.getByTestId("pivot-panel")).toContainText("non-basic cards scored");
  await page.getByTestId("pivot-include-all").check();
  const rows = page.getByTestId("pivot-row");
  await expect(rows.first()).toBeVisible({ timeout: SLOW });
  expect(await rows.count()).toBeGreaterThan(1);
  await expect(page.getByTestId("pivot-baseline")).toContainText("Wayta");
  await expect(rows.first().locator("[data-reason-sentence]")).toContainText("EDHREC");
  await expect(rows.first()).not.toContainText("UNKNOWN");
  await rows.first().locator("img, [data-card]").first().click({ button: "right" });
  const menu = page.getByRole("menu");
  await expect(menu).toContainText("Set as commander");
  await expect(menu).not.toContainText("Add to deck");
  await expect(menu).not.toContainText("Remove from deck");
  await page.keyboard.press("Escape");
  await rows.first().getByTestId("pivot-list").click();
  await expect(page.getByTestId("pivot-off-color").first()).toBeVisible();
  expect(errors, errors.join("\n")).toEqual([]);
  expect(bad, bad.join("\n")).toEqual([]);
});
