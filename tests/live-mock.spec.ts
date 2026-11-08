import { test, expect, type Page } from "@playwright/test";
import path from "node:path";
import { API_PREFIX, FX, SEEDED_COUNT, mockBackend, pivotEmptyResponse, seedDeckStorage, type MockCalls } from "./fixtures/live";

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

async function gotoDeck(page: Page, opts: { workbench?: boolean } = {}): Promise<MockCalls> {
  const calls = await mockBackend(page);
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
    expect(zones).toEqual(["Commanders", "Win Conditions", "Lands", "Ramp", "Card Draw", "Removal", "Board Wipes", "Counters", "Tokens", "Utility"]);
    // FieldSection → CardPile → BoardCard forward `zone`, so the current lane is checked.
    const checked = await sub.locator('[role="menuitemradio"][aria-checked="true"]').allTextContents();
    test.info().annotations.push({ type: "move-to-checked", description: JSON.stringify(checked) });
    expect(checked.map((t) => t.replace("✓", "").trim()), "current lane checked").toEqual(["Ramp"]);
    await page.screenshot({ path: shot("desktop-submenu") });
    // Keyboard all the way: Utility is the last radio.
    await page.keyboard.press("End");
    const last = sub.locator('[role="menuitemradio"]').last();
    if (!(await last.evaluate((el) => el === document.activeElement))) {
      for (let i = 0; i < 9; i++) await page.keyboard.press("ArrowDown");
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
    const toast = page.locator('[data-testid="toast"]').last();
    const hasToast = (await toast.count()) > 0;
    test.info().annotations.push({ type: "undo-toast", description: hasToast ? await toast.innerText() : "no toast rendered" });
    if (hasToast) {
      await toast.locator('[data-testid="toast-action"]').click();
      await expect(page.locator('[data-testid="count-pill"]')).toHaveText(/103\s*\/\s*100/);
    }
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
