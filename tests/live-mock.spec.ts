import { test, expect, type Page } from "@playwright/test";
import path from "node:path";
import { API_PREFIX, FX, SEEDED_COUNT, mockBackend, pivotEmptyResponse, seedDeckStorage, zoneFor, type MockCalls } from "./fixtures/live";

/*
 * LIVE app (/deck-doctor) with every backend call mocked via page.route — no :8001.
 * Projects: live-mock-desktop (1440×900), live-mock-mobile (390×844, touch).
 * Fixtures: tests/fixtures/live (real cards copied from data/cards.json).
 * Screenshots: docs/plans/screens/live-*.png
 */

const SCREENS = path.resolve(__dirname, "..", "docs", "plans", "screens");
const shot = (name: string) => path.join(SCREENS, `live-${name}.png`);

const PREVIEW = '[data-testid="card-preview"]';
const MENU = '[data-testid="card-menu"] [role="menu"]';
const FIND = '[data-surface="find"]';
const FIND_CARD = `${FIND} [data-card-id]`;
const BOARD_CARD = '[data-testid="engine-col-neutral"] [data-card-id][data-context="deck"]';

type Box = { x: number; y: number; width: number; height: number };
const intersects = (a: Box, b: Box) =>
  a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y;

async function gotoDeck(
  page: Page,
  opts: { workbench?: boolean; before?: (page: Page) => Promise<void> } = {},
): Promise<MockCalls> {
  const calls = await mockBackend(page);
  // Routes registered later win in Playwright, so per-test overrides go here.
  if (opts.before) await opts.before(page);
  await seedDeckStorage(page, opts);
  // Deterministic screenshots: the gallery's ?motion=0 only exists on /dev/ui-kit.
  await page.addInitScript(() => {
    document.addEventListener("DOMContentLoaded", () => {
      document.documentElement.dataset.motion = "0";
    });
  });
  await page.goto(`/deck-doctor${opts.workbench ? "?workbench=1" : ""}`);
  await page.waitForSelector('[data-testid="commander-strip"] [data-card-id]');
  await page.mouse.move(2, 2);
  return calls;
}

/** Switch the left panel to the Search tab and wait for the mocked Find grid. */
async function openFind(page: Page) {
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page.waitForSelector(FIND_CARD);
}

const findCard = (page: Page, n: number) => page.locator(FIND_CARD).nth(n);

async function hoverCenter(page: Page, n: number) {
  const card = findCard(page, n);
  await card.scrollIntoViewIfNeeded();
  const b = (await card.boundingBox())!;
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2);
  return b;
}

/** The board column (EngineBoard root): everything between the search panel and the rail. */
const boardBox = async (page: Page) =>
  (await page.locator('[data-testid="commander-strip"]').locator("..").boundingBox())!;

// ---------------------------------------------------------------- Load
test.describe("Live deck page (mocked backend)", () => {
  test("L1 seeded deck renders: commander, 103 cards, board piles, no unexpected API calls", async ({ page }) => {
    const calls = await gotoDeck(page);
    await expect(page.locator('[data-testid="commander-strip"]')).toContainText(FX.commander.name);
    await expect(page.locator("header").first()).toContainText(`${SEEDED_COUNT} cards`);
    // Every seeded non-basic card is on the board as a solid pile card.
    for (const c of FX.deck.slice(0, 5)) {
      await expect(page.locator(`[data-card-id="${c.id}"][data-context="deck"]`).first()).toBeVisible();
    }
    expect(await page.locator(BOARD_CARD).count()).toBeGreaterThanOrEqual(FX.deck.length);
    await page.waitForTimeout(400);
    expect(calls.paths()).toEqual(expect.arrayContaining(["/auth/me", "/templates", "/deck/analyze", "/deck/diagnose"]));
    expect(calls.unexpected).toEqual([]);
    await page.screenshot({ path: shot(page.viewportSize()!.width < 500 ? "mobile-board" : "desktop-board"), fullPage: false });
  });

  test("L2 no horizontal page scroll", async ({ page, viewport }) => {
    await gotoDeck(page);
    const sw = await page.evaluate(() => document.documentElement.scrollWidth);
    test.info().annotations.push({ type: "scrollWidth", description: `${sw} @ viewport ${viewport!.width}` });
    expect(sw).toBeLessThanOrEqual(viewport!.width);
  });
});

// ---------------------------------------------------------------- Preview
test.describe("Preview on the live Find grid", () => {
  test.skip(({ isMobile }) => Boolean(isMobile), "pointer-only");

  test("P1 hover → preview beside the Find grid, not over it; records board overlap", async ({ page }) => {
    await gotoDeck(page);
    await openFind(page);
    expect(await page.locator(FIND_CARD).count()).toBe(FX.find.length);
    // Tiles must not overlap each other (soft: evidence for the layout finding, see report).
    const tiles = await page.locator(FIND_CARD).evaluateAll((els) =>
      els.slice(0, 4).map((e) => {
        const r = e.getBoundingClientRect();
        return { x: r.x, y: r.y, width: r.width, height: r.height };
      }),
    );
    const grid = await page.locator(FIND).evaluate((e) => getComputedStyle(e).gridTemplateColumns + " | rows " + getComputedStyle(e).gridTemplateRows.slice(0, 40));
    test.info().annotations.push({ type: "find-grid", description: `${grid} tiles=${JSON.stringify(tiles)}` });
    expect.soft(intersects(tiles[0], tiles[1]), "tile 0/1 overlap").toBe(false);
    expect.soft(intersects(tiles[0], tiles[2]), "tile 0/2 overlap").toBe(false);
    // Hover the top-left corner region: the only part of tile 0 no neighbour covers today.
    const b0 = (await findCard(page, 0).boundingBox())!;
    await page.mouse.move(b0.x + 20, b0.y + 20);
    await page.waitForTimeout(100);
    expect(await page.locator(PREVIEW).count()).toBe(0); // < 120 ms: nothing yet
    await page.waitForTimeout(100);
    const preview = page.locator(PREVIEW);
    await expect(preview).toHaveCount(1);
    expect(await preview.getAttribute("data-anchor-id")).toBe(FX.find[0].id);
    expect(await preview.evaluate((el) => getComputedStyle(el).pointerEvents)).toBe("none");
    const pb = (await preview.boundingBox())!;
    const fb = (await page.locator(FIND).boundingBox())!;
    const bb = await boardBox(page);
    const fits = await preview.getAttribute("data-fits");
    test.info().annotations.push({
      type: "preview-placement",
      description: `fits=${fits} preview=${JSON.stringify(pb)} find=${JSON.stringify(fb)} overlapsBoard=${intersects(pb, bb)}`,
    });
    expect(pb.width).toBeGreaterThanOrEqual(240);
    expect(pb.width).toBeLessThanOrEqual(336);
    expect(fits).toBe("true");
    expect(intersects(pb, fb)).toBe(false); // beside the grid, never over it
    expect(pb.x).toBeGreaterThanOrEqual(fb.x + fb.width); // to the right of the search panel
    await page.screenshot({ path: shot("desktop-preview") });
  });

  test("P2 slipping ≤ 6 px off the card keeps the preview; leaving for 200 ms hides it", async ({ page }) => {
    await gotoDeck(page);
    await openFind(page);
    const b = (await findCard(page, 1).boundingBox())!;
    await page.mouse.move(b.x + b.width - 20, b.y + 20); // top-right region of tile 1 (uncovered)
    await page.waitForTimeout(170);
    await expect(page.locator(PREVIEW)).toHaveCount(1);
    expect(await page.locator(PREVIEW).getAttribute("data-anchor-id")).toBe(FX.find[1].id);
    // 3 px past the right edge: inside the tolerance box.
    await page.mouse.move(b.x + b.width + 3, b.y + 20);
    await page.waitForTimeout(220);
    await expect(page.locator(PREVIEW)).toHaveCount(1);
    // Far away: the 150 ms close timer runs out.
    await page.mouse.move(b.x - 60, b.y - 60);
    await page.waitForTimeout(220);
    await expect(page.locator(PREVIEW)).toHaveCount(0);
  });

  test("P3 hovering a board pile card previews it beside the pile", async ({ page }) => {
    await gotoDeck(page);
    const card = page.locator(BOARD_CARD).first();
    await card.scrollIntoViewIfNeeded();
    const b = (await card.boundingBox())!;
    await page.mouse.move(b.x + 10, b.y + b.height / 2);
    await page.waitForTimeout(200);
    const preview = page.locator(PREVIEW);
    await expect(preview).toHaveCount(1);
    const pb = (await preview.boundingBox())!;
    const sb = (await card.locator("xpath=ancestor::*[@data-surface][1]").boundingBox())!;
    test.info().annotations.push({ type: "pile-preview", description: `fits=${await preview.getAttribute("data-fits")} preview=${JSON.stringify(pb)} pile=${JSON.stringify(sb)}` });
    if ((await preview.getAttribute("data-fits")) === "true") expect(intersects(pb, sb)).toBe(false);
  });
});

// ---------------------------------------------------------------- Context menu
test.describe("Context menu on the live board", () => {
  test.skip(({ isMobile }) => Boolean(isMobile), "pointer/keyboard only");

  const labels = (page: Page) =>
    page.locator(`${MENU} [role^="menuitem"]`).evaluateAll((els) =>
      els.map((e) => (e.querySelector(".dd-menu-label")?.textContent ?? e.textContent ?? "").replace("↗", "").trim()),
    );

  test("M1 right-click a board card → deck actions in plan order; Find card → Add to deck first", async ({ page }) => {
    await gotoDeck(page);
    const card = page.locator(BOARD_CARD).first();
    await card.scrollIntoViewIfNeeded();
    // Tucked piles overlap by 44 px; the first card's left strip is the visible part.
    await card.click({ button: "right", position: { x: 10, y: 30 } });
    await expect(page.locator(MENU)).toBeVisible({ timeout: 500 });
    expect(await page.locator(PREVIEW).count()).toBe(0);
    expect(await labels(page)).toEqual([
      "Remove from deck",
      "Move to …",
      "Mark as cut candidate",
      "Swap for a better card",
      "Similar cards",
      "Synergizes with",
      "Played with",
      "Combos & engines",
      "Find cards that do this…",
      "View on Scryfall",
      "ManaPool",
      "TCGplayer",
      "Amazon",
    ]);
    const mb = (await page.locator(MENU).boundingBox())!;
    const vp = page.viewportSize()!;
    expect(mb.x + mb.width).toBeLessThanOrEqual(vp.width - 8);
    expect(mb.y + mb.height).toBeLessThanOrEqual(vp.height - 8);
    await page.screenshot({ path: shot("desktop-menu") });
    await page.keyboard.press("Escape");
    await expect(page.locator(MENU)).toHaveCount(0);

    // Commander: Krenko IS the commander → no "Set as commander".
    await page.locator('[data-testid="commander-strip"] [data-card-id]').first().click({ button: "right", position: { x: 10, y: 40 } });
    await expect(page.locator(MENU)).toBeVisible();
    const cl = await labels(page);
    expect(cl[0]).toBe("Remove from deck");
    expect(cl).not.toContain("Set as commander");
    expect(cl).not.toContain("Move to …");
    await page.keyboard.press("Escape");

    await openFind(page);
    // position: the tiles overlap today (see P1), so hit the uncovered top-left corner.
    await findCard(page, 0).click({ button: "right", position: { x: 20, y: 20 } });
    await expect(page.locator(MENU)).toBeVisible();
    const fl = await labels(page);
    expect(fl[0]).toBe("Add to deck");
    // Krenko, Tin Street Kingpin is a legendary creature in the Find grid → offered as commander.
    await page.keyboard.press("Escape");
    const kingpin = FX.find.find((c) => c.name === "Krenko, Tin Street Kingpin")!;
    // Its neighbour's hover action bar covers it (overlap finding) → open via keyboard instead.
    const kc = page.locator(`${FIND} [data-card-id="${kingpin.id}"]`);
    await kc.scrollIntoViewIfNeeded();
    await kc.focus();
    await page.keyboard.press("Shift+F10");
    await expect(page.locator(MENU)).toBeVisible();
    expect(await labels(page)).toContain("Set as commander");
    await page.keyboard.press("Escape");
  });

  test("M2 Move to … submenu lists every zone with the current lane checked, and moves the card", async ({ page }) => {
    await gotoDeck(page);
    const solRing = FX.deck.find((c) => c.name === "Sol Ring")!;
    const card = page.locator(`[data-testid="engine-col-neutral"] [data-card-id="${solRing.id}"][data-context="deck"]`).first();
    await card.scrollIntoViewIfNeeded();
    await card.focus();
    await page.keyboard.press("Shift+F10");
    const items = page.locator(`${MENU} [role^="menuitem"]`);
    await expect(items.first()).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("ArrowRight");
    const sub = page.locator('.dd-submenu [role="menu"]');
    await expect(sub).toBeVisible();
    const zones = await sub.locator('[role="menuitemradio"]').evaluateAll((els) => els.map((e) => e.textContent?.replace("✓", "").trim()));
    // F-03: Commanders is only reachable through "Set as commander" (validated), never Move.
    expect(zones).toEqual(["Win Conditions", "Lands", "Ramp", "Card Draw", "Removal", "Board Wipes", "Counters", "Tokens", "Utility"]);
    // FieldSection → CardPile → BoardCard forward `zone`, so the current lane is checked.
    const checked = await sub.locator('[role="menuitemradio"][aria-checked="true"]').allTextContents();
    test.info().annotations.push({ type: "move-to-checked", description: JSON.stringify(checked) });
    expect(checked.map((t) => t.replace("✓", "").trim()), "current lane checked").toEqual(["Ramp"]);
    await page.screenshot({ path: shot("desktop-submenu") });
    // Keyboard all the way: Utility is the last radio.
    await page.keyboard.press("End");
    const last = sub.locator('[role="menuitemradio"]').last();
    if (!(await last.evaluate((el) => el === document.activeElement))) {
      for (let i = 0; i < 8; i++) await page.keyboard.press("ArrowDown");
    }
    await expect(last).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.locator(MENU)).toHaveCount(0);
    const zone = await page.evaluate(
      (id) => JSON.parse(localStorage.getItem("simmander.deck")!).state.cards[id].zone,
      solRing.id,
    );
    expect(zone).toBe("Utility");
  });
});

// ---------------------------------------------------------------- Keyboard
test.describe("Keyboard path on the live page", () => {
  test.skip(({ isMobile }) => Boolean(isMobile), "keyboard only");

  test("K1 Tab reaches the Find grid (one stop) → preview after 250 ms → Esc hides → Shift+F10 menu → Enter adds", async ({ page }) => {
    await gotoDeck(page);
    await openFind(page);
    const card = findCard(page, 0);
    await page.locator("h1").first().evaluate((el) => {
      (el as HTMLElement).tabIndex = -1;
      (el as HTMLElement).focus();
    });
    let tabs = 0;
    while (tabs++ < 60 && !(await card.evaluate((el) => el === document.activeElement))) {
      await page.keyboard.press("Tab");
    }
    test.info().annotations.push({ type: "tabs-to-find", description: String(tabs) });
    await expect(card).toBeFocused();
    await page.waitForTimeout(320);
    await expect(page.locator(PREVIEW)).toHaveCount(1);
    await page.keyboard.press("Escape");
    await expect(page.locator(PREVIEW)).toHaveCount(0);
    await expect(card).toBeFocused();
    // Arrow keys rove inside the surface.
    await page.keyboard.press("ArrowRight");
    await expect(findCard(page, 1)).toBeFocused();
    await page.keyboard.press("ArrowLeft");
    await expect(card).toBeFocused();

    await page.keyboard.press("Shift+F10");
    const items = page.locator(`${MENU} [role^="menuitem"]`);
    await expect(items.first()).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await expect(items.nth(1)).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(page.locator(MENU)).toHaveCount(0);
    await expect(card).toBeFocused();

    // Enter = primary (Add to deck) on a Find card → the header count goes up by one.
    await page.keyboard.press("Enter");
    await expect(page.locator("header").first()).toContainText(`${SEEDED_COUNT + 1} cards`);
    await expect(page.locator(`[data-card-id="${FX.find[0].id}"][data-context="deck"]`).first()).toBeVisible();
    // Ctrl+Z undoes it (useUndoHotkeys).
    await page.keyboard.press("Control+z");
    await expect(page.locator("header").first()).toContainText(`${SEEDED_COUNT} cards`);
  });
});

// ---------------------------------------------------------------- Drag and drop
test.describe("Drag and drop on the live board", () => {
  test.skip(({ isMobile }) => Boolean(isMobile), "pointer only");

  test("D1 dragging Lightning Bolt from Removal to Utility re-homes it (dnd-kit, 6 px activation)", async ({ page }) => {
    await gotoDeck(page);
    const bolt = FX.deck.find((c) => c.name === "Lightning Bolt")!;
    const col = page.locator('[data-testid="engine-col-neutral"]');
    const section = (zone: string) => col.locator("div.rounded-lg").filter({ has: page.locator("span.font-display", { hasText: new RegExp(`^${zone}$`) }) });
    const card = section("Removal").locator(`[data-card-id="${bolt.id}"][data-context="deck"]`);
    await expect(card).toHaveCount(1);
    // The neutral column is taller than the viewport: scroll Removal to the top so Utility
    // (four sections below) is on screen too — dnd-kit needs both under the pointer path.
    await section("Removal").evaluate((el) => el.scrollIntoView({ block: "start" }));
    const target = section("Utility");
    const cb = (await card.boundingBox())!;
    const tb = (await target.boundingBox())!;
    const vp = page.viewportSize()!;
    test.info().annotations.push({ type: "drag-geometry", description: `card=${JSON.stringify(cb)} target=${JSON.stringify(tb)}` });
    expect(tb.y + tb.height / 2).toBeLessThan(vp.height);
    // Grab the visible left strip of the tucked card.
    const sx = cb.x + 12;
    const sy = cb.y + cb.height / 2;
    await page.mouse.move(sx, sy);
    await page.mouse.down();
    await page.mouse.move(sx + 4, sy + 4); // below the 6 px activation distance
    await page.mouse.move(sx + 12, sy + 12, { steps: 3 }); // activates
    await page.mouse.move(tb.x + tb.width / 2, tb.y + tb.height / 2, { steps: 15 });
    await page.waitForTimeout(80);
    await page.mouse.up();
    // Solid in Utility; the old home (Removal, from its mechanic tag) keeps an "additional" ghost.
    await expect(section("Utility").locator(`[data-card-id="${bolt.id}"]:not([data-ghost])`)).toHaveCount(1);
    await expect(section("Removal").locator(`[data-card-id="${bolt.id}"]:not([data-ghost])`)).toHaveCount(0);
    await expect(section("Removal").locator(`[data-card-id="${bolt.id}"][data-ghost="additional"]`)).toHaveCount(1);
    const zone = await page.evaluate(
      (id) => JSON.parse(localStorage.getItem("simmander.deck")!).state.cards[id].zone,
      bolt.id,
    );
    expect(zone).toBe("Utility");
    // A completed drag must not open the context menu.
    await page.waitForTimeout(150);
    expect(await page.locator(MENU).count()).toBe(0);
    await page.screenshot({ path: shot("desktop-after-drag") });
  });
});

// ---------------------------------------------------------------- Workbench
test.describe("?workbench=1 (DeckHeader + DoctorRail, mocked endpoints)", () => {
  test("W1 header + rail render; all five tabs are fed by the mocks", async ({ page, isMobile }) => {
    const calls = await gotoDeck(page, { workbench: true });
    const header = page.locator('[data-testid="deck-header"]');
    const rail = page.locator('[data-testid="doctor-rail"]');
    await expect(header).toBeVisible();
    await expect(header).toContainText(FX.commander.name);
    const pill = page.locator('[data-testid="count-pill"]');
    await expect(pill).toHaveText(/103\s*\/\s*100\s*·\s*3 over/);
    await expect(page.locator('[data-testid="bracket-vital"]')).toContainText("Bracket");
    const mobile = Boolean(isMobile);
    const name = (t: string) => shot(`${mobile ? "mobile" : "desktop"}-workbench-${t}`);

    // Desktop: tabs sit on top of the right rail. Mobile (§4.9): a 56 px bottom tab bar
    // whose tap opens the rail as a bottom sheet above the bar.
    const TABS = mobile ? '[data-testid="rail-tabbar"]' : '[data-testid="rail-tabs"]';
    const tabs = page.locator(`${TABS} [role="tab"]`);
    await expect(tabs).toHaveCount(5);
    expect(await tabs.evaluateAll((els) => els.map((e) => e.getAttribute("data-tab")))).toEqual(["suggest", "cuts", "tuneup", "combos", "pivot"]);
    if (mobile) {
      await expect(rail).toHaveCount(0);
      await page.locator(`${TABS} [data-tab="suggest"]`).click();
      await expect(page.locator('[data-testid="rail-sheet"]')).toBeVisible();
    }
    await expect(rail).toBeVisible();

    // Suggest (default tab) ← /deck/recommend
    const rows = page.locator('[data-testid="suggest-panel"] [data-testid="rail-row"]');
    await expect(rows).toHaveCount(FX.find.length);
    await expect(page.locator('[data-testid="suggest-panel"]')).toContainText("EDHREC");
    for (let i = 0; i < 3; i++) await expect(rows.nth(i).locator("[data-reason-sentence]")).toHaveCount(1);
    await page.screenshot({ path: name("suggest") });

    // Cuts ← /deck/cuts?to_100=true&target=3 (103 cards → 3 over)
    await page.locator(`${TABS} [data-tab="cuts"]`).click();
    await expect(page.locator('[data-testid="cuts-target"]')).toHaveValue("3");
    await expect(page.locator('[data-testid="cuts-over-by"]')).toHaveText("3 over");
    await expect(page.locator('[data-testid="cuts-panel"] [data-testid="rail-row"]')).toHaveCount(3);
    await expect(page.locator('[data-testid="cuts-panel"]')).toContainText("Wild Guess");
    await page.screenshot({ path: name("cuts") });

    // Tune-up ← /deck/upgrade-sweep
    await page.locator('[data-tab="tuneup"]').click();
    await expect(page.locator('[data-testid="sweep-swap"]')).toHaveCount(3);
    await expect(page.locator('[data-testid="tuneup-panel"]')).toContainText("Light Up the Stage");
    await page.screenshot({ path: name("tuneup") });

    // Combos ← /deck/combos
    await page.locator('[data-tab="combos"]').click();
    await expect(page.locator('[data-testid="combos-complete"]')).toContainText("Thornbite Staff");
    await expect(page.locator('[data-testid="combos-near"]')).toContainText("add Conspicuous Snoop");
    await page.screenshot({ path: name("combos") });

    // Pivot ← /deck/pivot
    await page.locator('[data-tab="pivot"]').click();
    await expect(page.locator('[data-testid="pivot-baseline"]')).toContainText(FX.commander.name);
    await expect(page.locator('[data-testid="pivot-panel"] [data-testid="pivot-row"]')).toHaveCount(2);
    await page.screenshot({ path: name("pivot") });

    expect(calls.paths()).toEqual(
      expect.arrayContaining(["/deck/analyze", "/deck/recommend", "/deck/cuts", "/deck/upgrade-sweep", "/deck/combos", "/deck/pivot"]),
    );
    expect(calls.all.some((c) => c.path === "/deck/cuts" && c.search.includes("to_100=true") && c.search.includes("target=3"))).toBe(true);
    expect(calls.unexpected).toEqual([]);

    // Layout (§4.1): header ≤ 96 px spanning the board column, rail beside the board,
    // the board's Neutral column fully inside the board (never clipped).
    if (!mobile) {
      const hb = (await header.boundingBox())!;
      const rb = (await rail.boundingBox())!;
      const bb = await boardBox(page);
      const nb = (await page.locator('[data-testid="engine-col-neutral"]').boundingBox())!;
      test.info().annotations.push({ type: "workbench-layout", description: `header=${JSON.stringify(hb)} rail=${JSON.stringify(rb)} board=${JSON.stringify(bb)} neutral=${JSON.stringify(nb)}` });
      expect(hb.height, "deck header height").toBeLessThanOrEqual(96);
      expect(hb.width, "deck header spans the board").toBeGreaterThanOrEqual(bb.width);
      expect(hb.y + hb.height).toBeLessThanOrEqual(bb.y + 1);
      expect(intersects(rb, bb)).toBe(false);
      expect(nb.x + nb.width).toBeLessThanOrEqual(bb.x + bb.width + 1);
    } else {
      // §4.9: the bar is the bottom 56 px, the sheet sits above it, and Find is reachable from the header.
      const vp = page.viewportSize()!;
      const barBox = (await page.locator('[data-testid="rail-tabbar"]').boundingBox())!;
      expect(barBox.y + barBox.height).toBeGreaterThanOrEqual(vp.height - 1);
      const sheetBox = (await page.locator('[data-testid="rail-sheet"]').boundingBox())!;
      expect(sheetBox.y + sheetBox.height).toBeLessThanOrEqual(barBox.y + 1);
      await page.locator(`${TABS} [data-tab="pivot"]`).click(); // same tab again → closes
      await expect(page.locator('[data-testid="rail-sheet"]')).toHaveCount(0);
      await page.locator('[data-testid="open-find"]').click();
      const findPanel = page.locator('[data-testid="find-panel"]');
      await expect(findPanel).toBeVisible();
      await expect(findPanel.getByRole("button", { name: "Search", exact: true })).toBeVisible();
      const findBox = (await findPanel.boundingBox())!;
      expect(findBox.width).toBeLessThanOrEqual(vp.width);
      await page.screenshot({ path: name("find") });
      await page.locator('[data-testid="close-find"]').click();
      await expect(page.locator('[data-testid="commander-strip"]')).toBeVisible();
    }
  });

  test("W2 adding from Suggest shows an Undo toast and bumps the count pill", async ({ page, isMobile }) => {
    test.skip(Boolean(isMobile), "desktop composition");
    await gotoDeck(page, { workbench: true });
    const rows = page.locator('[data-testid="suggest-panel"] [data-testid="rail-row"]');
    await expect(rows).toHaveCount(FX.find.length);
    await rows.first().locator('button[title="Add to deck"]').click();
    await expect(page.locator('[data-testid="count-pill"]')).toHaveText(/104\s*\/\s*100/);
    await expect(rows).toHaveCount(FX.find.length - 1);
    // F-06: the rail's + goes through useUndoableDeck, so it always gets an Undo toast.
    const toast = page.locator('[data-testid="toast"]').last();
    await expect(toast).toContainText("Undo");
    await toast.locator('[data-testid="toast-action"]').click();
    await expect(page.locator('[data-testid="count-pill"]')).toHaveText(/103\s*\/\s*100/);
  });

  test("W3 cuts: reason rows, quota warning, cut all, undo restores the count", async ({ page, isMobile }) => {
    await gotoDeck(page, { workbench: true });
    const mobile = Boolean(isMobile);
    const tabs = mobile ? '[data-testid="rail-tabbar"]' : '[data-testid="rail-tabs"]';
    await page.locator(`${tabs} [data-tab="cuts"]`).click();
    const panel = page.locator('[data-testid="cuts-panel"]');
    const rows = panel.locator('[data-testid="rail-row"]');
    await expect(rows).toHaveCount(3);
    await expect(rows.nth(0).locator("[data-reason-sentence]")).toContainText("fixture:");
    await expect(rows.nth(0)).toContainText("Card Draw");
    const warn = panel.locator('[data-breaks-quota="true"]');
    await expect(warn).toHaveCount(1);
    await expect(warn).toContainText("Sol Ring");
    await expect(warn).toContainText("Below quota");
    await expect(warn.locator('button[title^="Cut anyway"]')).toHaveText("Cut anyway");
    await warn.scrollIntoViewIfNeeded();
    await page.screenshot({ path: shot(mobile ? "mobile-workbench-cuts-warn" : "desktop-workbench-cuts-warn") });

    const pill = page.locator('[data-testid="count-pill"]');
    await expect(pill).toHaveText(/103\s*\/\s*100/);
    await panel.locator('[data-testid="cuts-all"]').click();
    await expect(pill).toHaveText(/101\s*\/\s*100/);
    const toast = page.locator('[data-testid="toast"]').last();
    await expect(toast).toContainText("Undo");
    await toast.locator('[data-testid="toast-action"]').click();
    await expect(pill).toHaveText(/103\s*\/\s*100/);

    await rows.first().locator('button[title="Cut from deck"]').click();
    await expect(pill).toHaveText(/102\s*\/\s*100/);
    await page.locator('[data-testid="toast"]').last().locator('[data-testid="toast-action"]').click();
    await expect(pill).toHaveText(/103\s*\/\s*100/);
  });

  test("W4 pivot: reason, evidence chips, off-colour list, include all", async ({ page, isMobile }) => {
    await gotoDeck(page, { workbench: true });
    const mobile = Boolean(isMobile);
    const tabs = mobile ? '[data-testid="rail-tabbar"]' : '[data-testid="rail-tabs"]';
    await page.locator(`${tabs} [data-tab="pivot"]`).click();
    const panel = page.locator('[data-testid="pivot-panel"]');
    await expect(panel.locator('[data-testid="pivot-baseline"]')).toContainText(FX.commander.name);
    await expect(panel.locator('[data-testid="pivot-baseline"]')).toContainText("score");
    const rows = panel.locator('[data-testid="pivot-row"]');
    await expect(rows).toHaveCount(2);
    const muxus = rows.filter({ hasText: "Muxus, Goblin Grandee" });
    await expect(muxus.locator("[data-reason-sentence]")).toContainText("fixture:");
    await expect(muxus).toContainText("coverage");
    await expect(muxus).toContainText("inclusion");
    await expect(muxus).toContainText("synergy");
    const meren = rows.filter({ hasText: "Meren of Clan Nel Toth" });
    await expect(meren).toContainText("off-colour");
    await meren.locator('[data-testid="pivot-list"]').click();
    const off = panel.locator('[data-testid="pivot-off-color"]');
    await expect(off).toContainText("Lightning Bolt");
    await off.scrollIntoViewIfNeeded();
    await expect(page.locator('[data-testid="commander-strip"]')).toContainText(FX.commander.name);
    await expect(page.locator('[data-testid="commander-strip"]')).not.toContainText("Meren");
    await page.screenshot({ path: shot(mobile ? "mobile-workbench-pivot" : "desktop-workbench-pivot") });

    const req = page.waitForRequest((r) => r.url().includes("/deck/pivot") && r.url().includes("include_all=true"));
    await panel.locator('[data-testid="pivot-include-all"]').check();
    await req;
    await expect(rows).toHaveCount(3);
    await expect(rows.filter({ hasText: "Karador, Ghost Chieftain" })).toContainText("Does not beat the baseline");
  });

  test("W5 pivot empty state when no candidate beats the commander", async ({ page, isMobile }) => {
    await gotoDeck(page, { workbench: true });
    await page.route(`**${API_PREFIX}/deck/pivot**`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(pivotEmptyResponse()),
      }),
    );
    const mobile = Boolean(isMobile);
    const tabs = mobile ? '[data-testid="rail-tabbar"]' : '[data-testid="rail-tabs"]';
    await page.locator(`${tabs} [data-tab="pivot"]`).click();
    const panel = page.locator('[data-testid="pivot-panel"]');
    await expect(panel).toContainText(`No candidate beats ${FX.commander.name}`);
    await expect(panel.locator('[data-testid="pivot-include-all"]')).toBeVisible();
    await expect(panel.locator('[data-testid="pivot-row"]')).toHaveCount(0);
    await page.screenshot({ path: shot(mobile ? "mobile-workbench-pivot-empty" : "desktop-workbench-pivot-empty") });
  });

  test("W6 cuts: repeated basics get unique rows (no duplicate React keys) and Cut all removes every copy; target field can be cleared", async ({ page, isMobile }) => {
    const errors: string[] = [];
    page.on("console", (m) => {
      if (m.type() === "error" || m.type() === "warning") errors.push(m.text());
    });
    await gotoDeck(page, { workbench: true });
    // The backend emits one row per card copy: three Forests share one card id.
    const forestRow = (i: number) => ({
      card: FX.basic,
      contribution: 0.01 + i / 100,
      reasons: [],
      role: "land",
      role_before: 40,
      role_after: 39 - i,
      quota: 37,
      quota_after: 39 - i,
      curve_bin: null,
      curve_before: null,
      curve_after: null,
      curve_ideal: null,
      breaks_quota: false,
      reason: `fixture: surplus basic land (copy ${i + 1})`,
    });
    await page.route(`**${API_PREFIX}/deck/cuts**`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ cuts: [forestRow(0), forestRow(1), forestRow(2)], over_by: 3, target: 3, shortfall: 0 }),
      }),
    );
    // The cuts query already ran against the default mock (it is not gated on the visible tab),
    // so reload to make the page fetch through the override above.
    await page.reload();
    await page.waitForSelector('[data-testid="commander-strip"] [data-card-id]');
    const mobile = Boolean(isMobile);
    const tabs = mobile ? '[data-testid="rail-tabbar"]' : '[data-testid="rail-tabs"]';
    await page.locator(`${tabs} [data-tab="cuts"]`).click();
    const panel = page.locator('[data-testid="cuts-panel"]');
    await expect(panel.locator('[data-testid="rail-row"]')).toHaveCount(3);
    await expect(panel.locator('[data-testid="rail-row"]').first()).toContainText("copy 1");

    // Typing: the field may be emptied (no snap back to 1 mid-edit) and restores on blur.
    const target = panel.locator('[data-testid="cuts-target"]');
    await target.fill("");
    await expect(target).toHaveValue("");
    await target.blur();
    await expect(target).not.toHaveValue("");

    const pill = page.locator('[data-testid="count-pill"]');
    await expect(pill).toHaveText(/103\s*\/\s*100/);
    await panel.locator('[data-testid="cuts-all"]').click();
    await expect(pill).toHaveText(/100\s*\/\s*100/);
    await page.locator('[data-testid="toast"]').last().locator('[data-testid="toast-action"]').click();
    await expect(pill).toHaveText(/103\s*\/\s*100/);
    expect(errors.filter((e) => /same key|unique "key"/i.test(e))).toEqual([]);
  });

  test("W8 cuts: Cut all stops at the overage when the target field asks for more", async ({ page, isMobile }) => {
    await gotoDeck(page, { workbench: true });
    const row = (i: number) => ({
      card: FX.basic, contribution: 0.01 + i / 100, reasons: [], role: "land", role_before: 40, role_after: 39 - i,
      quota: 37, quota_after: 39 - i, curve_bin: null, curve_before: null, curve_after: null, curve_ideal: null,
      breaks_quota: false, reason: `fixture: surplus basic land (copy ${i + 1})`,
    });
    // Deck is 103; the user asked for 5 cuts. The backend returns 5 rows but only 3 are needed to reach 100.
    await page.route(`**${API_PREFIX}/deck/cuts**`, (route) =>
      route.fulfill({ status: 200, contentType: "application/json",
        body: JSON.stringify({ cuts: [0, 1, 2, 3, 4].map(row), over_by: 3, target: 5, shortfall: 0 }) }),
    );
    await page.reload();
    await page.waitForSelector('[data-testid="commander-strip"] [data-card-id]');
    const tabs = isMobile ? '[data-testid="rail-tabbar"]' : '[data-testid="rail-tabs"]';
    await page.locator(`${tabs} [data-tab="cuts"]`).click();
    const panel = page.locator('[data-testid="cuts-panel"]');
    await expect(panel.locator('[data-testid="rail-row"]')).toHaveCount(5);
    await expect(panel.locator('[data-testid="cuts-all"]')).toHaveText("Cut all 3");
    await panel.locator('[data-testid="cuts-all"]').click();
    await expect(page.locator('[data-testid="count-pill"]')).toHaveText(/100\s*\/\s*100/);
  });

  test("W7 pivot candidates get a commander-appropriate menu: no 'Add to deck' / 'Remove', but 'Set as commander'", async ({ page, isMobile }) => {
    test.skip(Boolean(isMobile), "right-click menu is a pointer path; touch uses the sheet");
    await gotoDeck(page, { workbench: true });
    await page.locator('[data-testid="rail-tabs"] [data-tab="pivot"]').click();
    const panel = page.locator('[data-testid="pivot-panel"]');
    const row = panel.locator('[data-testid="pivot-row"]').filter({ hasText: "Muxus, Goblin Grandee" });
    await row.locator("[data-card-id]").first().click({ button: "right" });
    const menu = page.locator(MENU);
    await expect(menu).toBeVisible();
    await expect(menu).toContainText("Set as commander");
    await expect(menu).not.toContainText("Add to deck");
    await expect(menu).not.toContainText("Remove from deck");
    await page.keyboard.press("Escape");
  });
});

// ---------------------------------------------------------------- Review triage 2026-11-24
// One test per confirmed finding of the cross-family review (docs/plans/2026-11-24-frontend-review-triage.md).
const HEADER = (page: Page) => page.locator("header").first();
const PILL = '[data-testid="count-pill"]';
const neutralLane = (page: Page, zone: string) =>
  page.locator(`[data-testid="engine-col-neutral"] [data-zone-lane="${zone}"]`);
const laneCount = (page: Page, zone: string) => neutralLane(page, zone).locator(":scope > div").first().locator("span").last();

/** A cut_to_100 row for `card` (fixture numbers, labelled). */
const cutRow = (card: (typeof FX)["basic"], i: number) => ({
  card, contribution: 0.01 + i / 100, reasons: [], role: "land", role_before: 40, role_after: 39 - i,
  quota: 37, quota_after: 39 - i, curve_bin: null, curve_before: null, curve_after: null, curve_ideal: null,
  breaks_quota: false, reason: `fixture: cut row ${i + 1}`,
});

/** Logged-in user + one saved deck (Krenko, the 35 fixture cards, 20 Mountains). Records every PUT body. */
async function mockSavedDeck(page: Page) {
  const id = "fx-saved-deck";
  const basicQty = 20;
  const cards = [
    { card: FX.commander, zone: "Commanders", quantity: 1 },
    ...FX.deck.map((c) => ({ card: c, zone: zoneFor(c), quantity: 1 })),
    { card: FX.basic, zone: "Lands", quantity: basicQty },
  ];
  const count = 1 + FX.deck.length + basicQty;
  const stamp = "2026-11-01T00:00:00Z";
  const detail = { id, name: "Fixture saved deck", commander_id: FX.commander.id, created_at: stamp, updated_at: stamp, cards };
  const puts: { cards: { id: string; zone: string; quantity: number }[] }[] = [];
  const json = (body: unknown) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  await page.route(`**${API_PREFIX}/auth/me`, (r) => r.fulfill(json({ user: { id: 1 } })));
  await page.route(`**${API_PREFIX}/decks**`, async (route) => {
    const req = route.request();
    const p = new URL(req.url()).pathname;
    if (req.method() === "GET" && p.endsWith("/decks"))
      return route.fulfill(json([{ id, name: detail.name, commander_id: FX.commander.id, card_count: count, updated_at: stamp }]));
    if (req.method() === "GET" && p.endsWith(`/decks/${id}`)) return route.fulfill(json(detail));
    if (req.method() === "PUT" && p.endsWith(`/decks/${id}`)) {
      puts.push(req.postDataJSON());
      return route.fulfill(json(detail));
    }
    return route.fallback();
  });
  return { count, puts };
}

async function loadSavedDeck(page: Page, count: number) {
  await page.locator('[data-testid="open-decks"]').click();
  await page.locator('[data-testid="deck-row"] button').first().click();
  await expect(HEADER(page)).toContainText(`${count} cards`);
}

test.describe("Review triage 2026-11-24 (mocked backend)", () => {
  test("F-01 loading a saved deck is ONE undo step: Ctrl+Z restores the pre-load deck", async ({ page, isMobile }) => {
    test.skip(Boolean(isMobile), "header Decks button is desktop composition");
    let saved!: Awaited<ReturnType<typeof mockSavedDeck>>;
    await gotoDeck(page, { before: async (p) => void (saved = await mockSavedDeck(p)) });
    await loadSavedDeck(page, saved.count);
    await page.keyboard.press("Control+z");
    await expect(HEADER(page)).toContainText(`${SEEDED_COUNT} cards`);
  });

  test("F-05 a zone-only move on an open saved deck is autosaved to the server", async ({ page, isMobile }) => {
    test.skip(Boolean(isMobile), "keyboard/menu path");
    let saved!: Awaited<ReturnType<typeof mockSavedDeck>>;
    await gotoDeck(page, { before: async (p) => void (saved = await mockSavedDeck(p)) });
    await loadSavedDeck(page, saved.count);
    // Let the post-load autosave (2 s debounce) land first, so only the move can explain a later PUT.
    await expect.poll(() => saved.puts.length, { timeout: 6000 }).toBeGreaterThan(0);
    await page.waitForTimeout(2500);
    const putsBefore = saved.puts.length;
    const solRing = FX.deck.find((c) => c.name === "Sol Ring")!;
    const card = page.locator(`[data-testid="engine-col-neutral"] [data-card-id="${solRing.id}"][data-context="deck"]`).first();
    await card.scrollIntoViewIfNeeded();
    await card.focus();
    await page.keyboard.press("Shift+F10");
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("ArrowRight");
    await page.locator('.dd-submenu [role="menuitemradio"]', { hasText: "Utility" }).click();
    await expect
      .poll(() => saved.puts.slice(putsBefore).some((b) => b.cards.find((e) => e.id === solRing.id)?.zone === "Utility"), { timeout: 6000 })
      .toBe(true);
  });

  test("F-02a the board's Lands lane counts basic copies (67 Mountains → 67, not 1)", async ({ page }) => {
    await gotoDeck(page);
    const nonbasicLands = FX.deck.filter((c) => zoneFor(c) === "Lands").length;
    await expect(laneCount(page, "Lands")).toHaveText(String(FX.basicQuantity + nonbasicLands));
  });

  test("F-02b Remove from deck on a basic removes one copy", async ({ page, isMobile }) => {
    test.skip(Boolean(isMobile), "keyboard/menu path");
    await gotoDeck(page);
    const mtn = page.locator(`[data-testid="engine-col-neutral"] [data-card-id="${FX.basic.id}"][data-context="deck"]`).first();
    await mtn.scrollIntoViewIfNeeded();
    await mtn.focus();
    await page.keyboard.press("Shift+F10");
    await expect(page.locator(`${MENU} [role^="menuitem"]`).first()).toHaveText(/Remove from deck/);
    await page.keyboard.press("Enter");
    await expect(HEADER(page)).toContainText(`${SEEDED_COUNT - 1} cards`);
  });

  test("F-02c adding a basic from Find bumps its quantity (no second singleton pile)", async ({ page, isMobile }) => {
    test.skip(Boolean(isMobile), "keyboard path");
    await gotoDeck(page, {
      before: (p) =>
        p.route(`**${API_PREFIX}/cards?**`, (route) =>
          route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([FX.basic, ...FX.find]) }),
        ),
    });
    await openFind(page);
    const mtnFind = page.locator(`${FIND} [data-card-id="${FX.basic.id}"]`);
    await mtnFind.focus();
    await page.keyboard.press("Enter");
    await expect(HEADER(page)).toContainText(`${SEEDED_COUNT + 1} cards`);
    await expect(page.locator(`[data-testid="engine-col-neutral"] [data-card-id="${FX.basic.id}"][data-context="deck"]`)).toHaveCount(1);
    const stored = await page.evaluate(() => JSON.parse(localStorage.getItem("simmander.deck")!).state);
    expect(stored.cards[FX.basic.id]).toBeUndefined();
    expect(stored.basics[FX.basic.id].quantity).toBe(FX.basicQuantity + 1);
  });

  test("F-04 a Commanders-zone card returned by /deck/cuts is never offered as a cut", async ({ page, isMobile }) => {
    const wild = FX.deck.find((c) => c.name === "Wild Guess")!;
    await gotoDeck(page, {
      workbench: true,
      before: (p) =>
        p.route(`**${API_PREFIX}/deck/cuts**`, (route) =>
          route.fulfill({ status: 200, contentType: "application/json",
            body: JSON.stringify({ cuts: [cutRow(FX.commander, 0), cutRow(wild, 1)], over_by: 3, target: 3, shortfall: 0 }) }),
        ),
    });
    const tabs = isMobile ? '[data-testid="rail-tabbar"]' : '[data-testid="rail-tabs"]';
    await page.locator(`${tabs} [data-tab="cuts"]`).click();
    const panel = page.locator('[data-testid="cuts-panel"]');
    await expect(panel.locator(`[data-testid="rail-row"][data-card-id="${wild.id}"]`)).toHaveCount(1);
    await expect(panel.locator(`[data-testid="rail-row"][data-card-id="${FX.commander.id}"]`)).toHaveCount(0);
  });

  test("F-08a Cut all never cuts below 100 when the response has no over_by", async ({ page, isMobile }) => {
    await gotoDeck(page, {
      workbench: true,
      before: (p) =>
        p.route(`**${API_PREFIX}/deck/cuts**`, (route) =>
          route.fulfill({ status: 200, contentType: "application/json",
            body: JSON.stringify({ cuts: [0, 1, 2, 3, 4].map((i) => cutRow(FX.basic, i)), target: 5, shortfall: 0 }) }),
        ),
    });
    const tabs = isMobile ? '[data-testid="rail-tabbar"]' : '[data-testid="rail-tabs"]';
    await page.locator(`${tabs} [data-tab="cuts"]`).click();
    const panel = page.locator('[data-testid="cuts-panel"]');
    await panel.locator('[data-testid="cuts-target"]').fill("5");
    await expect(panel.locator('[data-testid="rail-row"]')).toHaveCount(5);
    await expect(panel.locator('[data-testid="cuts-all"]')).toHaveText("Cut all 3");
    await panel.locator('[data-testid="cuts-all"]').click();
    await expect(page.locator(PILL)).toHaveText(/100\s*\/\s*100/);
  });

  test("F-08b the pill's cut target follows the deck when it grows", async ({ page, isMobile }) => {
    test.skip(Boolean(isMobile), "desktop composition");
    await gotoDeck(page, { workbench: true });
    await page.locator(PILL).click();
    await expect(page.locator('[data-testid="cuts-target"]')).toHaveValue("3");
    await page.locator('[data-testid="rail-tabs"] [data-tab="suggest"]').click();
    const add = page.locator('[data-testid="suggest-panel"] [data-testid="rail-row"] button[title="Add to deck"]');
    await add.first().click();
    await expect(page.locator(PILL)).toHaveText(/104\s*\/\s*100/);
    await add.first().click();
    await expect(page.locator(PILL)).toHaveText(/105\s*\/\s*100/);
    await page.locator('[data-testid="rail-tabs"] [data-tab="cuts"]').click();
    await expect(page.locator('[data-testid="cuts-target"]')).toHaveValue("5");
  });

  test("F-06 board Delete and Suggest + both get an Undo toast", async ({ page, isMobile }) => {
    test.skip(Boolean(isMobile), "keyboard path");
    await gotoDeck(page, { workbench: true });
    await page.locator('[data-testid="suggest-panel"] [data-testid="rail-row"] button[title="Add to deck"]').first().click();
    await expect(page.locator('[data-testid="toast"]').last()).toContainText(`Added ${FX.find[0].name}`);
    const solRing = FX.deck.find((c) => c.name === "Sol Ring")!;
    const card = page.locator(`[data-testid="engine-col-neutral"] [data-card-id="${solRing.id}"][data-context="deck"]`).first();
    await card.scrollIntoViewIfNeeded();
    await card.focus();
    await page.keyboard.press("Delete");
    await expect(page.locator('[data-testid="toast"]').last()).toContainText("Removed Sol Ring");
  });

  test("F-07 a stale toast Undo does not undo a different action", async ({ page, isMobile }) => {
    test.skip(Boolean(isMobile), "desktop composition");
    await gotoDeck(page, { workbench: true });
    const pill = page.locator(PILL);
    await page.locator('[data-testid="suggest-panel"] [data-testid="rail-row"] button[title="Add to deck"]').first().click();
    await expect(pill).toHaveText(/104\s*\/\s*100/);
    await page.locator('[data-testid="rail-tabs"] [data-tab="cuts"]').click();
    const wild = page.locator('[data-testid="cuts-panel"] [data-testid="rail-row"]').filter({ hasText: "Wild Guess" });
    await wild.locator('button[title="Cut from deck"]').click();
    await expect(pill).toHaveText(/103\s*\/\s*100/);
    const cutToast = page.locator('[data-testid="toast"]').filter({ hasText: "Removed Wild Guess" });
    await expect(cutToast).toHaveCount(1);
    await page.keyboard.press("Control+z"); // undoes the cut
    await expect(pill).toHaveText(/104\s*\/\s*100/);
    await cutToast.locator('[data-testid="toast-action"]').click(); // stale: must not remove the added card
    await expect(pill).toHaveText(/104\s*\/\s*100/);
  });

  test("F-10 a pending hover-open does not preview a row that unmounted", async ({ page, isMobile }) => {
    test.skip(Boolean(isMobile), "pointer only");
    await gotoDeck(page, { workbench: true });
    const rows = page.locator('[data-testid="suggest-panel"] [data-testid="rail-row"]');
    await expect(rows).toHaveCount(FX.find.length);
    const last = rows.last();
    const id = (await last.getAttribute("data-card-id"))!;
    const thumb = last.locator(`[data-card-id="${id}"]`).first();
    await thumb.scrollIntoViewIfNeeded();
    await thumb.focus();
    const b = (await thumb.boundingBox())!;
    await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2);
    await page.keyboard.press("Enter"); // primary = add → the row is filtered out (< 120 ms)
    await expect(rows).toHaveCount(FX.find.length - 1);
    await page.waitForTimeout(400);
    await expect(page.locator(`${PREVIEW}[data-anchor-id="${id}"]`)).toHaveCount(0);
  });

  test("F-11 keyboard Cut keeps focus inside the Cuts list", async ({ page, isMobile }) => {
    test.skip(Boolean(isMobile), "keyboard path");
    await gotoDeck(page, { workbench: true });
    await page.locator('[data-testid="rail-tabs"] [data-tab="cuts"]').click();
    const panel = page.locator('[data-testid="cuts-panel"]');
    await expect(panel.locator('[data-testid="rail-row"]')).toHaveCount(3);
    await panel.locator('button[title="Cut from deck"]').first().focus();
    await page.keyboard.press("Enter");
    await expect(page.locator(PILL)).toHaveText(/102\s*\/\s*100/);
    await page.waitForTimeout(300);
    expect(await page.evaluate(() => !!document.activeElement?.closest('[data-testid="cuts-panel"]'))).toBe(true);
  });

  test("F-12 the rail sheet takes focus, returns it on close, and fits a short viewport", async ({ page, isMobile }) => {
    test.skip(!isMobile, "mobile sheet only");
    await gotoDeck(page, { workbench: true });
    const tab = page.locator('[data-testid="rail-tabbar"] [data-tab="cuts"]');
    await tab.click();
    const sheet = page.locator('[data-testid="rail-sheet"]');
    await expect(sheet).toBeVisible();
    await expect.poll(() => page.evaluate(() => !!document.activeElement?.closest('[data-testid="rail-sheet"]'))).toBe(true);
    await page.keyboard.press("Escape");
    await expect(sheet).toHaveCount(0);
    await expect(tab).toBeFocused();
    await page.setViewportSize({ width: 390, height: 360 });
    await tab.click();
    await sheet.locator('button[aria-label="Expand sheet"]').click();
    const sb = (await sheet.boundingBox())!;
    expect(sb.y).toBeGreaterThanOrEqual(0);
  });

  test("F-13 the rail sheet does not survive a trip through the desktop breakpoint", async ({ page, isMobile }) => {
    test.skip(!isMobile, "mobile sheet only");
    await gotoDeck(page, { workbench: true });
    await page.locator('[data-testid="rail-tabbar"] [data-tab="suggest"]').click();
    await expect(page.locator('[data-testid="rail-sheet"]')).toBeVisible();
    await page.setViewportSize({ width: 1200, height: 900 });
    await expect(page.locator('[data-testid="rail-tabs"]')).toBeVisible();
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.locator('[data-testid="rail-tabbar"]')).toBeVisible();
    await expect(page.locator('[data-testid="rail-sheet"]')).toHaveCount(0);
  });

  test("F-14 rail tabs: one tab stop, arrow keys move + select, tabpanel is labelled", async ({ page, isMobile }) => {
    test.skip(Boolean(isMobile), "keyboard path");
    await gotoDeck(page, { workbench: true });
    const tabs = page.locator('[data-testid="rail-tabs"] [role="tab"]');
    expect(await tabs.evaluateAll((els) => els.map((e) => (e as HTMLElement).tabIndex))).toEqual([0, -1, -1, -1, -1]);
    await tabs.first().focus();
    await page.keyboard.press("ArrowRight");
    await expect(tabs.nth(1)).toBeFocused();
    await expect(tabs.nth(1)).toHaveAttribute("aria-selected", "true");
    await page.keyboard.press("End");
    await expect(tabs.nth(4)).toBeFocused();
    await page.keyboard.press("Home");
    await expect(tabs.nth(0)).toBeFocused();
    const panelId = await tabs.nth(0).getAttribute("aria-controls");
    expect(panelId).toBeTruthy();
    const panel = page.locator(`[id="${panelId}"]`);
    await expect(panel).toHaveAttribute("role", "tabpanel");
    await expect(panel).toHaveAttribute("aria-labelledby", (await tabs.nth(0).getAttribute("id"))!);
  });

  test("F-17 a persisted deck hydrates without a server/client mismatch", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (m) => {
      if (m.type() === "error") errors.push(m.text());
    });
    await gotoDeck(page);
    await page.waitForTimeout(500);
    // Evidence for the triage doc: what the server HTML says before the client store loads.
    const html = (await (await page.request.get("/deck-doctor")).text()).replace(/<!-- -->/g, "");
    test.info().annotations.push({ type: "ssr-card-count", description: (html.match(/\d+ cards/g) ?? []).join(" | ") || "none" });
    expect(errors.filter((e) => /hydrat|did not match|does not match/i.test(e))).toEqual([]);
  });

  test("F-09 failed Suggest / Combos / analyze requests show an error, not an empty state", async ({ page, isMobile }) => {
    test.skip(Boolean(isMobile), "desktop composition");
    const fail = (route: import("@playwright/test").Route) =>
      route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "fixture: 500" }) });
    await gotoDeck(page, {
      workbench: true,
      before: async (p) => {
        await p.route(`**${API_PREFIX}/deck/recommend**`, fail);
        await p.route(`**${API_PREFIX}/deck/combos**`, fail);
        await p.route(`**${API_PREFIX}/deck/analyze**`, fail);
      },
    });
    const suggest = page.locator('[data-testid="suggest-panel"]');
    await expect(suggest).toContainText(/failed/i);
    await expect(suggest).not.toContainText("Nothing left to suggest");
    await expect(page.locator('[data-testid="bracket-vital"]')).toContainText(/failed/i);
    await page.locator('[data-testid="rail-tabs"] [data-tab="combos"]').click();
    await expect(page.locator('[data-testid="combos-panel"]')).toContainText(/failed/i);
  });

  test("F-15 Delete on a focused board card moves focus to a neighbour, not <body>", async ({ page, isMobile }) => {
    test.skip(Boolean(isMobile), "keyboard path");
    await gotoDeck(page);
    const solRing = FX.deck.find((c) => c.name === "Sol Ring")!;
    const card = page.locator(`[data-testid="engine-col-neutral"] [data-card-id="${solRing.id}"][data-context="deck"]`).first();
    await card.scrollIntoViewIfNeeded();
    await card.focus();
    await page.keyboard.press("Delete");
    await expect(HEADER(page)).toContainText(`${SEEDED_COUNT - 1} cards`);
    await expect.poll(() => page.evaluate(() => document.activeElement?.getAttribute("data-context") ?? document.activeElement?.tagName)).toBe("deck");
  });

  test("F-16 Mark as cut candidate shows on the board card", async ({ page, isMobile }) => {
    test.skip(Boolean(isMobile), "keyboard/menu path");
    await gotoDeck(page);
    const solRing = FX.deck.find((c) => c.name === "Sol Ring")!;
    const card = page.locator(`[data-testid="engine-col-neutral"] [data-card-id="${solRing.id}"][data-context="deck"]`).first();
    await card.scrollIntoViewIfNeeded();
    await card.focus();
    await page.keyboard.press("Shift+F10");
    await page.locator(`${MENU} [role^="menuitem"]`, { hasText: "Mark as cut candidate" }).click();
    await expect(card).toHaveAttribute("data-cut", "true");
  });

  test("F-19 Combos member chips open the card in the explorer", async ({ page, isMobile }) => {
    test.skip(Boolean(isMobile), "desktop composition");
    await gotoDeck(page, { workbench: true });
    await page.locator('[data-testid="rail-tabs"] [data-tab="combos"]').click();
    const chip = page.locator('[data-testid="combos-complete"] button', { hasText: "Thornbite Staff" }).first();
    await chip.click();
    await expect(page.locator('[data-testid="relationship-explorer"]')).toBeVisible();
  });

  test("F-20 Set as commander on an in-deck, in-colour legend reports no phantom pruned cards", async ({ page, isMobile }) => {
    test.skip(Boolean(isMobile), "keyboard/menu path");
    await gotoDeck(page);
    await openFind(page);
    const kingpin = FX.find.find((c) => c.name === "Krenko, Tin Street Kingpin")!;
    const kc = page.locator(`${FIND} [data-card-id="${kingpin.id}"]`);
    await kc.scrollIntoViewIfNeeded();
    await kc.focus();
    await page.keyboard.press("Enter"); // add it to the deck first
    await expect(HEADER(page)).toContainText(`${SEEDED_COUNT + 1} cards`);
    const board = page.locator(`[data-testid="engine-col-neutral"] [data-card-id="${kingpin.id}"][data-context="deck"]`).first();
    await board.scrollIntoViewIfNeeded();
    await board.focus();
    await page.keyboard.press("Shift+F10");
    await page.locator(`${MENU} [role^="menuitem"]`, { hasText: "Set as commander" }).click();
    const t = page.locator('[data-testid="toast"]').filter({ hasText: "is now the commander" });
    await expect(t).toHaveCount(1);
    await expect(t).not.toContainText("off-color");
  });

  test("F-22 on mobile, key 2 opens the rail sheet on Cuts", async ({ page, isMobile }) => {
    test.skip(!isMobile, "mobile only");
    await gotoDeck(page, { workbench: true });
    await page.locator("h1").first().click();
    await page.keyboard.press("2");
    await expect(page.locator('[data-testid="rail-sheet"]')).toBeVisible();
    await expect(page.locator('[data-testid="rail-tabbar"] [data-tab="cuts"]')).toHaveAttribute("aria-selected", "true");
  });

  test("B touch targets in the mobile Cuts sheet and the toast are ≥ 44 px", async ({ page, isMobile }) => {
    test.skip(!isMobile, "coarse pointer only");
    await gotoDeck(page, { workbench: true });
    await page.locator('[data-testid="rail-tabbar"] [data-tab="cuts"]').click();
    const sheet = page.locator('[data-testid="rail-sheet"]');
    const all = sheet.locator('[data-testid="cuts-all"]');
    await expect(all).toBeEnabled();
    expect((await all.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    expect((await sheet.locator('[data-testid="cuts-target"]').boundingBox())!.height).toBeGreaterThanOrEqual(44);
    await all.click();
    const undo = page.locator('[data-testid="toast"]').last().locator('[data-testid="toast-action"]');
    await expect(undo).toBeVisible();
    expect((await undo.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  });
});
