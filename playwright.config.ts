import { defineConfig, devices } from "@playwright/test";

/*
 * Projects:
 *   chromium            — the live-app spec (needs backend + data).
 *   ui-kit-desktop/laptop/mobile — tests/ui-kit.spec.ts against the backend-free
 *                         /deck-doctor/dev/ui-kit gallery (plan §9).
 * `webServer` starts the frontend dev server when nothing listens on :3000.
 */
export default defineConfig({
  testDir: "./tests",
  timeout: 30_000,
  retries: 0,
  use: {
    baseURL: "http://localhost:3000",
    headless: true,
  },
  webServer: {
    command: "npm run dev",
    cwd: "./frontend",
    url: "http://localhost:3000/deck-doctor/dev/ui-kit",
    reuseExistingServer: true,
    timeout: 120_000,
  },
  projects: [
    {
      name: "chromium",
      testMatch: /engine3.*\.spec\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "ui-kit-desktop",
      testMatch: /ui-kit\.spec\.ts/,
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
    {
      name: "ui-kit-laptop",
      testMatch: /ui-kit\.spec\.ts/,
      use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } },
    },
    {
      name: "ui-kit-mobile",
      testMatch: /ui-kit\.spec\.ts/,
      // iPhone 13 geometry + touch, driven by Chromium (WebKit is not installed here).
      use: { ...devices["iPhone 13"], browserName: "chromium" },
    },
    // live-mock-* — tests/live-mock.spec.ts: the real /deck-doctor page with every
    // backend call intercepted (page.route) and fed from tests/fixtures/live. No :8001.
    {
      name: "live-mock-desktop",
      testMatch: /live-mock\.spec\.ts/,
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
    {
      name: "live-mock-mobile",
      testMatch: /live-mock\.spec\.ts/,
      use: { ...devices["iPhone 13"], browserName: "chromium", viewport: { width: 390, height: 844 } },
    },
    // live-real — tests/live-real.spec.ts: REAL backend on :8001, no mocks.
    {
      name: "live-real-desktop",
      testMatch: /live-real\.spec\.ts/,
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
  ],
});
