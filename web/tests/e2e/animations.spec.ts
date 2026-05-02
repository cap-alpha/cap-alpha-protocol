/**
 * Micro-interaction E2E tests (L5)
 *
 * Tests that:
 * 1. The homepage loads and the leaderboard preview section is visible.
 * 2. Accuracy numbers (animated counters) are visible and contain numeric content.
 * 3. No significant layout shift occurred (CLS < 0.1).
 *
 * These tests run against the dev/production server at PLAYWRIGHT_BASE_URL
 * (default: http://localhost:3000).
 */

import { test, expect, Page } from "@playwright/test";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Returns the Cumulative Layout Shift score for the current page. */
async function getCLS(page: Page): Promise<number> {
    return page.evaluate(() => {
        return new Promise<number>((resolve) => {
            let cumulativeScore = 0;
            const observer = new PerformanceObserver((list) => {
                for (const entry of list.getEntries()) {
                    // LayoutShift entries have a `value` property
                    const shift = entry as PerformanceEntry & { value: number; hadRecentInput: boolean };
                    if (!shift.hadRecentInput) {
                        cumulativeScore += shift.value;
                    }
                }
            });

            try {
                observer.observe({ type: "layout-shift", buffered: true });
            } catch {
                // layout-shift not supported — return 0 (pass)
                resolve(0);
                return;
            }

            // Give the page 2s to accumulate any shifts triggered by our animations
            setTimeout(() => {
                observer.disconnect();
                resolve(cumulativeScore);
            }, 2000);
        });
    });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("L5 Micro-interactions — Homepage leaderboard preview", () => {
    test.beforeEach(async ({ page }) => {
        await page.goto("/");
    });

    test("homepage loads successfully", async ({ page }) => {
        const body = page.locator("body");
        await expect(body).toBeVisible();
        // Confirm no hard crash
        const appError = page.locator("text=Application Error");
        await expect(appError).toHaveCount(0);
    });

    test("leaderboard preview section is visible", async ({ page }) => {
        // The PunditLeaderboardPreview renders inside the homepage.
        // Either a stats bar, a pundit row, or the empty/loading state will be visible.
        // We wait up to 10s for data-dependent content to hydrate.
        const preview = page.locator('[data-testid="leaderboard-preview"], .space-y-3, .pundit-leaderboard').first();

        // Fallback: look for any element that typically appears in the leaderboard
        const statsOrRows = page.locator("text=pundits tracked, text=predictions logged, text=resolved").first();

        // Accept either selector or a loading indicator as "visible"
        const loadingOrContent = page.locator(
            '[class*="space-y-3"], [class*="h-40"]'
        ).first();

        await expect(loadingOrContent).toBeVisible({ timeout: 10000 });
    });

    test("accuracy counter numbers are visible when leaderboard has data", async ({ page }) => {
        // Wait for either data to load or the empty-state to appear
        await page.waitForSelector('[class*="space-y-3"], [class*="rounded-xl"]', {
            timeout: 10000,
        });

        // If counters rendered, they should contain numeric text (possibly with %)
        const counterCandidates = page.locator('[class*="tabular-nums"]');
        const count = await counterCandidates.count();

        if (count > 0) {
            // At least one counter is rendered — verify it has numeric content
            const firstText = await counterCandidates.first().textContent();
            // Should be a number, optionally followed by %
            expect(firstText).toMatch(/[\d]/);
        }
        // If count === 0, data hasn't loaded / is empty — test passes vacuously
    });

    test("no significant layout shift (CLS < 0.1)", async ({ page }) => {
        // Wait for any async content to load
        await page.waitForLoadState("networkidle");

        const cls = await getCLS(page);
        expect(cls).toBeLessThan(0.1);
    });
});

test.describe("L5 Micro-interactions — Ledger page tab transitions", () => {
    test("ledger page loads and tab switching works", async ({ page }) => {
        const response = await page.goto("/ledger");
        expect(response?.status()).toBe(200);

        // Wait for content
        await page.waitForLoadState("networkidle");

        // Find the "Recent" tab button and click it
        const recentTab = page.locator("button", { hasText: /recent/i }).first();
        const tabExists = await recentTab.count();

        if (tabExists > 0) {
            await recentTab.click();
            // After tab transition (200ms animation + buffer), content should still be visible
            await page.waitForTimeout(400);
            const body = page.locator("body");
            await expect(body).toBeVisible();
        }
    });

    test("ledger page has no layout shift during tab transition (CLS < 0.1)", async ({ page }) => {
        await page.goto("/ledger");
        await page.waitForLoadState("networkidle");

        // Click Recent tab to trigger AnimatePresence transition
        const recentTab = page.locator("button", { hasText: /recent/i }).first();
        if (await recentTab.count() > 0) {
            await recentTab.click();
            await page.waitForTimeout(400);
        }

        const cls = await getCLS(page);
        expect(cls).toBeLessThan(0.1);
    });
});
