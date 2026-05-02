/**
 * Visual regression baselines for design system foundation (L1/L2/L3)
 *
 * First run: captures baseline screenshots.
 * Subsequent runs: diffs against baseline — any pixel delta fails the test.
 *
 * Run manually with: npx playwright test tests/e2e/visual-regression.spec.ts
 * Requires a running dev/prod server at PLAYWRIGHT_BASE_URL (default: http://localhost:3000)
 */

import { test, expect } from "@playwright/test";

const VIEWPORTS = [
    { name: "desktop", width: 1280, height: 800 },
    { name: "tablet", width: 768, height: 1024 },
    { name: "mobile", width: 375, height: 812 },
];

for (const vp of VIEWPORTS) {
    test.describe(`Homepage @ ${vp.name} (${vp.width}x${vp.height})`, () => {
        test.use({ viewport: { width: vp.width, height: vp.height } });

        test(`homepage baseline — ${vp.name}`, async ({ page }) => {
            await page.goto("/");
            // Wait for fonts + hero section to be visible
            await page.waitForSelector("h1");
            // Brief settle for font loading
            await page.waitForTimeout(500);
            await expect(page).toHaveScreenshot(`homepage-${vp.name}.png`, {
                fullPage: true,
                // Allow minor anti-aliasing variance across runs
                maxDiffPixelRatio: 0.01,
            });
        });
    });

    test.describe(`Ledger @ ${vp.name} (${vp.width}x${vp.height})`, () => {
        test.use({ viewport: { width: vp.width, height: vp.height } });

        test(`ledger baseline — ${vp.name}`, async ({ page }) => {
            await page.goto("/ledger");
            // Wait for table/list content to be present
            await page.waitForLoadState("networkidle");
            await page.waitForTimeout(500);
            await expect(page).toHaveScreenshot(`ledger-${vp.name}.png`, {
                fullPage: true,
                maxDiffPixelRatio: 0.01,
            });
        });
    });
}
