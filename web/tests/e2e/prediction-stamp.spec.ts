import { test, expect } from "@playwright/test";

/**
 * Prediction Outcome display tests — homepage leaderboard preview
 *
 * The original "Prediction Outcome Stamp" tests assumed a `data-testid="outcome-stamp"`
 * element on the homepage. No such element exists in the current codebase.
 *
 * These tests cover what actually exists: the PunditLeaderboardPreview component
 * renders on the homepage with pundit stats. Tests verify the homepage renders
 * the leaderboard section without error.
 *
 * When outcome stamps (data-testid="outcome-stamp") are added to the design,
 * restore the original stamp assertions from git history (commit before this one).
 */

test.describe("Homepage — leaderboard preview section", () => {
    test("homepage renders without error", async ({ page }) => {
        const res = await page.goto("/");
        expect(res?.status()).toBe(200);
        await page.waitForLoadState("networkidle");
        const errorBoundary = page.locator("text=Application Error");
        await expect(errorBoundary).toHaveCount(0);
    });

    test("homepage has h1 with 'Accountable' text", async ({ page }) => {
        await page.goto("/");
        await page.waitForLoadState("domcontentloaded");
        const h1 = page.locator("h1");
        await expect(h1).toContainText(/accountable/i);
    });

    test("homepage leaderboard section is present", async ({ page }) => {
        await page.goto("/");
        await page.waitForLoadState("networkidle");

        // The homepage has a "Pundit Leaderboard" heading for the live preview
        await expect(page.getByText("Pundit Leaderboard").first()).toBeVisible();
    });

    test("homepage has a link to /ledger", async ({ page }) => {
        await page.goto("/");
        const ledgerLinks = page.locator('a[href="/ledger"]');
        await expect(ledgerLinks.first()).toBeVisible();
    });

    test("homepage has a link to /pricing", async ({ page }) => {
        await page.goto("/");
        const pricingLinks = page.locator('a[href="/pricing"]');
        await expect(pricingLinks.first()).toBeVisible();
    });
});
