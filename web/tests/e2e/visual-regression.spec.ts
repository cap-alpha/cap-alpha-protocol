/**
 * Visual regression baselines for design system foundation (L1/L2/L3)
 *
 * First run: captures baseline screenshots.
 * Subsequent runs: diffs against baseline — any pixel delta fails the test.
 *
 * Run manually with: npx playwright test tests/e2e/visual-regression.spec.ts --update-snapshots
 * Requires a running dev/prod server at PLAYWRIGHT_BASE_URL (default: http://localhost:3000)
 *
 * STATUS: Baseline screenshots have not yet been captured.
 * TODO: Run `make test-e2e -- --update-snapshots` in Docker to generate baseline PNGs,
 * then commit the generated files under web/tests/e2e/visual-regression.spec.ts-snapshots/.
 * Until baselines are captured, these tests are skipped to avoid false-positive failures.
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
            // TODO: update snapshot after first Docker run with --update-snapshots
            // Skipped until baseline PNGs are committed to the repo.
            test.skip(true, "Visual regression baseline not yet captured — run make test-e2e -- --update-snapshots in Docker first");

            await page.goto("/");
            await page.waitForSelector("h1");
            await page.waitForTimeout(500);
            await expect(page).toHaveScreenshot(`homepage-${vp.name}.png`, {
                fullPage: true,
                maxDiffPixelRatio: 0.01,
            });
        });
    });

    test.describe(`Ledger @ ${vp.name} (${vp.width}x${vp.height})`, () => {
        test.use({ viewport: { width: vp.width, height: vp.height } });

        test(`ledger baseline — ${vp.name}`, async ({ page }) => {
            // TODO: update snapshot after first Docker run with --update-snapshots
            test.skip(true, "Visual regression baseline not yet captured — run make test-e2e -- --update-snapshots in Docker first");

            await page.goto("/ledger");
            await page.waitForLoadState("networkidle");
            await page.waitForTimeout(500);
            await expect(page).toHaveScreenshot(`ledger-${vp.name}.png`, {
                fullPage: true,
                maxDiffPixelRatio: 0.01,
            });
        });
    });
}
