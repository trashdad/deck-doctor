import { test, expect, type Page } from "@playwright/test";

/*
 * Framework acceptance tests (plan §7.7) against the backend-free gallery.
 * Projects: ui-kit-desktop (1440×900), ui-kit-laptop (1280×800), ui-kit-mobile (iPhone 13, touch).
 */

const URL = "/deck-doctor/dev/ui-kit?motion=0";
const PREVIEW = '[data-testid="card-preview"]';
const MENU = '[data-testid="card-menu"] [role="menu"]';

type Box = { x: number; y: number; width: number; height: number };
const intersects = (a: Box, b: Box) =>
  a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y;

async function gotoKit(page: Page) {
  await page.goto(URL);
  await page.waitForSelector('[data-testid="kit-find"] [data-card-id]');
  // Park the pointer away from every card before each scenario.
  await page.mouse.move(2, 2);
}

function findCard(page: Page, n: number) {
  return page.locator('[data-testid="kit-find"] [data-card-id]').nth(n);
}

async function hoverCenter(page: Page, n: number) {
  await findCard(page, n).scrollIntoViewIfNeeded();
  const b = (await findCard(page, n).boundingBox())!;
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2);
  return b;
}

// ---------------------------------------------------------------- Preview
test.describe("Preview", () => {
  test.skip(({ isMobile }) => Boolean(isMobile), "pointer-only");

  test("P1 hovering for < 120 ms shows no preview", async ({ page }) => {
    await gotoKit(page);
    await hoverCenter(page, 0);
    await page.waitForTimeout(100);
    expect(await page.locator(PREVIEW).count()).toBe(0);
  });

  test("P2 preview exists after 150 ms, pointer-events none, width in [240,336], beside the surface", async ({ page }) => {
    await gotoKit(page);
    await hoverCenter(page, 0);
    await page.waitForTimeout(170);
    const preview = page.locator(PREVIEW);
    await expect(preview).toHaveCount(1);
    expect(await preview.evaluate((el) => getComputedStyle(el).pointerEvents)).toBe("none");
    const pb = (await preview.boundingBox())!;
    expect(pb.width).toBeGreaterThanOrEqual(240);
    expect(pb.width).toBeLessThanOrEqual(336);
    const fits = await preview.getAttribute("data-fits");
    const sb = (await page.locator('[data-testid="kit-find"]').boundingBox())!;
    if (fits === "true") expect(intersects(pb, sb)).toBe(false);
  });

  test("P3 moving to an adjacent card within 150 ms never unmounts the preview", async ({ page }) => {
    await gotoKit(page);
    await hoverCenter(page, 0);
    await page.waitForTimeout(170);
    await expect(page.locator(PREVIEW)).toHaveCount(1);
    const mountsBefore = await page.evaluate(() => window.__ddPreviewMounts ?? 0);
    const a = (await findCard(page, 0).boundingBox())!;
    const b = (await findCard(page, 1).boundingBox())!;
    // Sweep across the gap in a few steps (the gap is 12 px).
    await page.mouse.move(a.x + a.width - 2, a.y + a.height / 2);
    await page.mouse.move(a.x + a.width + 6, a.y + a.height / 2);
    await page.mouse.move(b.x + 2, b.y + b.height / 2);
    await page.waitForTimeout(60);
    await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2);
    await page.waitForTimeout(100);
    await expect(page.locator(PREVIEW)).toHaveCount(1);
    expect(await page.locator(PREVIEW).getAttribute("data-anchor-id")).toBe(await findCard(page, 1).getAttribute("data-card-id"));
    expect(await page.evaluate(() => window.__ddPreviewMounts ?? 0)).toBe(mountsBefore);
  });

  test("P4 leaving for 100 ms keeps it; leaving for 200 ms hides it", async ({ page }) => {
    await gotoKit(page);
    const box = await hoverCenter(page, 0);
    await page.waitForTimeout(170);
    await expect(page.locator(PREVIEW)).toHaveCount(1);
    // Far outside the 6 px tolerance box.
    await page.mouse.move(box.x - 40, box.y - 40);
    await page.waitForTimeout(100);
    await expect(page.locator(PREVIEW)).toHaveCount(1);
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.waitForTimeout(50);
    await expect(page.locator(PREVIEW)).toHaveCount(1);
    await page.mouse.move(box.x - 40, box.y - 40);
    await page.waitForTimeout(220);
    await expect(page.locator(PREVIEW)).toHaveCount(0);
  });

  test("P5 at 1280×800 a card at the right edge of the Find grid keeps the preview ≤ 1272", async ({ page, viewport }) => {
    test.skip(viewport?.width !== 1280, "laptop project only");
    await gotoKit(page);
    const cards = page.locator('[data-testid="kit-find"] [data-card-id]');
    const n = await cards.count();
    // Pick the right-most card of the first row.
    let best = 0;
    let bestX = -1;
    const firstTop = (await cards.nth(0).boundingBox())!.y;
    for (let i = 0; i < n; i++) {
      const b = (await cards.nth(i).boundingBox())!;
      if (Math.abs(b.y - firstTop) < 2 && b.x > bestX) {
        bestX = b.x;
        best = i;
      }
    }
    await hoverCenter(page, best);
    await page.waitForTimeout(170);
    const pb = (await page.locator(PREVIEW).boundingBox())!;
    expect(pb.x + pb.width).toBeLessThanOrEqual(1272);
    expect(pb.x).toBeGreaterThanOrEqual(8);
  });

  test("P6 ?motion=0 gives the preview a 0s transition", async ({ page }) => {
    await gotoKit(page);
    await hoverCenter(page, 0);
    await page.waitForTimeout(170);
    const dur = await page.locator(PREVIEW).evaluate((el) => getComputedStyle(el).transitionDuration);
    expect(dur.split(",").every((d) => d.trim() === "0s")).toBe(true);
  });

  test("P7 no preview while a menu or a dialog is open", async ({ page }) => {
    await gotoKit(page);
    await findCard(page, 2).click({ button: "right" });
    await expect(page.locator(MENU)).toBeVisible();
    await hoverCenter(page, 0);
    await page.waitForTimeout(200);
    expect(await page.locator(PREVIEW).count()).toBe(0);
    await page.keyboard.press("Escape");
    await expect(page.locator(MENU)).toHaveCount(0);
    await page.locator('[data-testid="open-dialog"]').click();
    await expect(page.locator('[data-testid="demo-dialog"]')).toBeVisible();
    await hoverCenter(page, 0);
    await page.waitForTimeout(200);
    expect(await page.locator(PREVIEW).count()).toBe(0);
  });

  test("P8 keyboard: focus → preview after 250 ms; Esc hides; focus stays", async ({ page }) => {
    await gotoKit(page);
    const card = findCard(page, 0);
    await card.scrollIntoViewIfNeeded();
    // Tab from a neighbour so :focus-visible applies.
    await page.locator("h1").first().evaluate((el) => {
      (el as HTMLElement).tabIndex = -1;
      (el as HTMLElement).focus();
    });
    // Find the surface's single Tab stop.
    await page.keyboard.press("Tab");
    let guard = 0;
    while (guard++ < 40 && !(await card.evaluate((el) => el === document.activeElement))) {
      await page.keyboard.press("Tab");
    }
    await expect(card).toBeFocused();
    await page.waitForTimeout(300);
    await expect(page.locator(PREVIEW)).toHaveCount(1);
    await page.keyboard.press("Escape");
    await expect(page.locator(PREVIEW)).toHaveCount(0);
    await expect(card).toBeFocused();
  });
});

// ---------------------------------------------------------------- Context menu
test.describe("Context menu", () => {
  test.skip(({ isMobile }) => Boolean(isMobile), "pointer/keyboard only");

  test("M1 right-click opens role=menu within 100 ms and prevents the native menu", async ({ page }) => {
    await gotoKit(page);
    const prevented = page.evaluate(
      () =>
        new Promise<boolean>((res) => {
          document.addEventListener("contextmenu", (e) => res(e.defaultPrevented), { once: true });
        }),
    );
    await findCard(page, 0).click({ button: "right" });
    await expect(page.locator(MENU)).toBeVisible({ timeout: 100 });
    expect(await prevented).toBe(true);
  });

  test("M2 action order per context", async ({ page }) => {
    await gotoKit(page);
    const labels = async () =>
      page.locator(`${MENU} [role^="menuitem"]`).evaluateAll((els) =>
        els.map((e) => (e.querySelector(".dd-menu-label")?.textContent ?? e.textContent ?? "").replace("↗", "").trim()),
      );
    await findCard(page, 0).click({ button: "right" });
    expect((await labels())[0]).toBe("Add to deck");
    await page.keyboard.press("Escape");
    const pileCard = page.locator('[data-testid="kit-pile"] [data-card-id]').first();
    // Tucked piles overlap by 44 px; the first card's left strip is the visible part.
    await pileCard.click({ button: "right", position: { x: 10, y: 30 } });
    const deckLabels = await labels();
    expect(deckLabels[0]).toBe("Remove from deck");
    expect(deckLabels).toEqual([
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
    await page.keyboard.press("Escape");
    // Commander context: Krenko is the commander → no "Set as commander".
    await page.locator('[data-testid="kit-commander"] [data-card-id]').first().click({ button: "right" });
    expect((await labels())[0]).toBe("Remove from deck");
    expect(await labels()).not.toContain("Set as commander");
    await page.keyboard.press("Escape");
    // The Ur-Dragon in the commander strip is a legendary creature that is NOT the commander.
    await page.locator('[data-testid="kit-commander"] [data-card-id]').nth(1).click({ button: "right" });
    expect(await labels()).toContain("Set as commander");
  });

  test("M3 Shift+F10 opens with focus on the first item; ↓ moves; Enter activates; Esc returns focus", async ({ page }) => {
    await gotoKit(page);
    const card = findCard(page, 0);
    await card.focus();
    await page.keyboard.press("Shift+F10");
    const items = page.locator(`${MENU} [role^="menuitem"]`);
    await expect(items.first()).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await expect(items.nth(1)).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(page.locator(MENU)).toHaveCount(0);
    await expect(card).toBeFocused();
    // Enter on "Add to deck" adds a card (live count goes up) and closes.
    const before = Number(await page.locator('[data-testid="deck-count-live"]').textContent());
    await page.keyboard.press("Shift+F10");
    await expect(items.first()).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.locator(MENU)).toHaveCount(0);
    await expect(page.locator('[data-testid="deck-count-live"]')).toHaveText(String(before + 1));
    await expect(card).toBeFocused();
  });

  test("M4 Move to … opens a submenu with every zone; the current one is checked", async ({ page }) => {
    await gotoKit(page);
    const pileCard = page.locator('[data-testid="kit-pile"] [data-card-id]').first();
    await pileCard.focus();
    await page.keyboard.press("Shift+F10");
    await page.keyboard.press("ArrowDown"); // Move to …
    await expect(page.locator(`${MENU} [role="menuitem"]`).nth(1)).toBeFocused();
    await page.keyboard.press("ArrowRight");
    const sub = page.locator('.dd-submenu [role="menu"]');
    await expect(sub).toBeVisible();
    const zones = await sub.locator('[role="menuitemradio"]').evaluateAll((els) => els.map((e) => e.textContent?.replace("✓", "").trim()));
    expect(zones).toEqual(["Commanders", "Win Conditions", "Lands", "Ramp", "Card Draw", "Removal", "Board Wipes", "Counters", "Tokens", "Utility"]);
    const checked = sub.locator('[role="menuitemradio"][aria-checked="true"]');
    await expect(checked).toHaveCount(1);
    await expect(checked).toHaveText(/Ramp/);
    await page.keyboard.press("ArrowLeft");
    await expect(sub).toHaveCount(0);
  });

  test("M5 the menu never overflows the viewport at any corner", async ({ page, viewport }) => {
    await gotoKit(page);
    for (const corner of ["tl", "tr", "bl", "br"]) {
      await page.locator(`[data-testid="menu-${corner}"]`).click();
      const box = (await page.locator(MENU).boundingBox())!;
      expect(box.x).toBeGreaterThanOrEqual(8);
      expect(box.y).toBeGreaterThanOrEqual(8);
      expect(box.x + box.width).toBeLessThanOrEqual(viewport!.width - 8);
      expect(box.y + box.height).toBeLessThanOrEqual(viewport!.height - 8);
      await page.keyboard.press("Escape");
      await expect(page.locator(MENU)).toHaveCount(0);
    }
    await page.locator('[data-testid="menu-keyboard"]').click();
    const kb = (await page.locator(MENU).boundingBox())!;
    expect(kb.x + kb.width).toBeLessThanOrEqual(viewport!.width - 8);
    expect(kb.y + kb.height).toBeLessThanOrEqual(viewport!.height - 8);
    await expect(page.locator(`${MENU} [role^="menuitem"]`).first()).toBeFocused();
  });

  test("M6 outside click, surface scroll > 8 px, and Back all close it", async ({ page }) => {
    await gotoKit(page);
    await findCard(page, 0).click({ button: "right" });
    await expect(page.locator(MENU)).toBeVisible();
    await page.mouse.click(4, 4);
    await expect(page.locator(MENU)).toHaveCount(0);

    await findCard(page, 0).click({ button: "right" });
    await expect(page.locator(MENU)).toBeVisible();
    await page.mouse.wheel(0, 120);
    await expect(page.locator(MENU)).toHaveCount(0);

    await findCard(page, 0).click({ button: "right" });
    await expect(page.locator(MENU)).toBeVisible();
    await page.goBack();
    await expect(page.locator(MENU)).toHaveCount(0);
    expect(page.url()).toContain("/dev/ui-kit");
  });
});

// ---------------------------------------------------------------- Touch
test.describe("Touch", () => {
  test.skip(({ isMobile }) => !isMobile, "mobile project only");

  test("T1 tap opens the sheet; long-press opens the sheet; no preview ever mounts", async ({ page }) => {
    await gotoKit(page);
    const card = findCard(page, 0);
    await card.tap();
    await expect(page.locator('[data-testid="card-sheet"]')).toBeVisible();
    expect(await page.locator(PREVIEW).count()).toBe(0);
    await page.keyboard.press("Escape");
    await expect(page.locator('[data-testid="card-sheet"]')).toHaveCount(0);

    const b = (await card.boundingBox())!;
    const cdp = await page.context().newCDPSession(page);
    const x = b.x + b.width / 2;
    const y = b.y + b.height / 2;
    await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x, y }] });
    await page.waitForTimeout(500);
    await expect(page.locator('[data-testid="card-sheet"]')).toBeVisible();
    await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
    expect(await page.locator(PREVIEW).count()).toBe(0);
    expect(await page.evaluate(() => window.__ddPreviewMounts ?? 0)).toBe(0);
  });

  test("T2 every tappable control in the sheet and the tab bar is ≥ 44×44", async ({ page }) => {
    await gotoKit(page);
    await findCard(page, 0).tap();
    const sheet = page.locator('[data-testid="card-sheet"]');
    await expect(sheet).toBeVisible();
    const boxes = await sheet.locator("button, a").evaluateAll((els) =>
      els.filter((e) => (e as HTMLElement).offsetParent !== null).map((e) => {
        const r = e.getBoundingClientRect();
        return { w: r.width, h: r.height, t: (e.textContent ?? "").trim() };
      }),
    );
    expect(boxes.length).toBeGreaterThan(5);
    for (const b of boxes) {
      expect(b.h, b.t).toBeGreaterThanOrEqual(44);
      expect(b.w, b.t).toBeGreaterThanOrEqual(44);
    }
    await page.keyboard.press("Escape");
    const tabs = await page.locator('[data-testid="rail-tabbar"] [role="tab"]').evaluateAll((els) =>
      els.map((e) => ({ w: e.getBoundingClientRect().width, h: e.getBoundingClientRect().height })),
    );
    expect(tabs.length).toBe(5);
    for (const t of tabs) {
      expect(t.h).toBeGreaterThanOrEqual(44);
      expect(t.w).toBeGreaterThanOrEqual(44);
    }
  });

  test("T3 no horizontal page scroll at 390 px", async ({ page }) => {
    await gotoKit(page);
    const sw = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(sw).toBeLessThanOrEqual(390);
  });
});

// ---------------------------------------------------------------- Workbench
test.describe("Workbench", () => {
  test.skip(({ isMobile }) => Boolean(isMobile), "desktop composition");

  test("W1 with Suggest open the board is unobscured at 5 sample points", async ({ page }) => {
    await gotoKit(page);
    await page.locator('[data-testid="rail-tabs"] [data-tab="suggest"]').click();
    const board = page.locator('[data-testid="engine-board"]');
    await board.scrollIntoViewIfNeeded();
    const b = (await board.boundingBox())!;
    const rail = (await page.locator('[data-testid="doctor-rail"]').boundingBox())!;
    const wb = (await page.locator('[data-testid="kit-workbench"] > div').last().boundingBox())!;
    expect(b.width / wb.width).toBeGreaterThanOrEqual(0.6);
    expect(rail.x).toBeGreaterThanOrEqual(b.x + b.width - 1);
    const pts = [
      [b.x + 10, b.y + 10],
      [b.x + b.width - 10, b.y + 10],
      [b.x + b.width / 2, b.y + b.height / 2],
      [b.x + 10, b.y + b.height - 10],
      [b.x + b.width - 10, b.y + b.height - 10],
    ];
    const ok = await page.evaluate((pts) => {
      const board = document.querySelector('[data-testid="engine-board"]')!;
      return pts.map(([x, y]) => {
        const el = document.elementFromPoint(x, y);
        return Boolean(el && board.contains(el));
      });
    }, pts);
    expect(ok).toEqual([true, true, true, true, true]);
  });

  test("W2 103-card pill reads '103 / 100 · 3 over' and opens Cuts with target 3", async ({ page }) => {
    await gotoKit(page);
    const pill = page.locator('[data-testid="kit-workbench"] [data-testid="count-pill"]');
    await expect(pill).toHaveText(/103\s*\/\s*100\s*·\s*3 over/);
    await pill.click();
    await expect(page.locator('[data-testid="rail-tabs"] [data-tab="cuts"]')).toHaveAttribute("aria-selected", "true");
    await expect(page.locator('[data-testid="cuts-target"]')).toHaveValue("3");
  });

  test("W3 every suggestion row has one sentence and ≤ 3 chips; every signal yields a sentence", async ({ page }) => {
    await gotoKit(page);
    const rows = page.locator('[data-testid="suggest-panel"] [data-testid="rail-row"]');
    expect(await rows.count()).toBeGreaterThan(0);
    for (let i = 0; i < (await rows.count()); i++) {
      await expect(rows.nth(i).locator("[data-reason-sentence]")).toHaveCount(1);
      expect(await rows.nth(i).locator("[data-reason-chip]").count()).toBeLessThanOrEqual(3);
    }
    const cases = page.locator('[data-testid="reason-case"] [data-reason-sentence]');
    const texts = await cases.allTextContents();
    expect(texts.length).toBeGreaterThanOrEqual(8);
    for (const t of texts) expect(t.trim().length).toBeGreaterThan(0);
  });

  test("W4 bracket vital starts with '≥ Bracket'", async ({ page }) => {
    await gotoKit(page);
    const vitals = page.locator('[data-testid="bracket-vital"]');
    for (let i = 0; i < (await vitals.count()); i++) {
      expect((await vitals.nth(i).innerText()).trim().startsWith("≥ Bracket")).toBe(true);
    }
  });

  test("W5 adding from Suggest shows a toast with Undo that restores the count", async ({ page }) => {
    await gotoKit(page);
    const live = page.locator('[data-testid="deck-count-live"]');
    const before = Number(await live.textContent());
    await page.locator('[data-testid="suggest-panel"] [data-testid="rail-row"] button[title="Add to deck"]').first().click();
    await expect(live).toHaveText(String(before + 1));
    const toast = page.locator('[data-testid="toast"]').last();
    await expect(toast).toContainText("Undo");
    await toast.locator('[data-testid="toast-action"]').click();
    await expect(live).toHaveText(String(before));
  });

  test("W6 no readable text < 11 px inside the rail or the deck header", async ({ page }) => {
    await gotoKit(page);
    const small = await page.evaluate(() => {
      const roots = Array.from(document.querySelectorAll('[data-testid="doctor-rail"], [data-testid="deck-header"]'));
      const bad: string[] = [];
      for (const root of roots) {
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
        let n: Node | null;
        while ((n = walker.nextNode())) {
          const text = (n.textContent ?? "").trim();
          if (!text) continue;
          const el = n.parentElement!;
          if (el.closest(".sr-only")) continue;
          const fs = parseFloat(getComputedStyle(el).fontSize);
          if (fs < 11) bad.push(`${text.slice(0, 30)} @ ${fs}px`);
        }
      }
      return bad;
    });
    expect(small).toEqual([]);
  });
});
