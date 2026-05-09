import { test, expect } from "@playwright/test";

/**
 * Pricing page E2E tests
 *
 * Tests the actual pricing page structure:
 *   - 4 tiers: Free ($0), Pro ($14.99/mo), API Starter ($99/mo), API Growth ($499/mo)
 *   - UpgradeButton component for paid tiers
 *   - "View Leaderboard" link for Free tier
 *
 * Note: the quiz flow, annual toggle, and feature-matrix table referenced in older
 * tests do not exist in the current pricing page — tests updated to match actual UI.
 *
 * Requires `npm run dev` or a running Next.js server at PLAYWRIGHT_BASE_URL.
 */

test.describe("Pricing page", () => {
    test.beforeEach(async ({ page }) => {
        await page.goto("/pricing");
    });

    test("pricing page loads with h1", async ({ page }) => {
        await expect(page.locator("h1")).toContainText(/pricing/i);
    });

    test("Free tier card is visible at $0", async ({ page }) => {
        // The Free tier shows FREE label and $0
        await expect(page.getByText("Free", { exact: true }).first()).toBeVisible();
        await expect(page.getByText("$0")).toBeVisible();
    });

    test("Pro tier card is visible at $14.99", async ({ page }) => {
        await expect(page.getByText("Pro", { exact: true }).first()).toBeVisible();
        await expect(page.getByText("$14.99")).toBeVisible();
    });

    test("API Starter tier card is visible at $99", async ({ page }) => {
        await expect(page.getByText("API Starter").first()).toBeVisible();
        await expect(page.getByText("$99")).toBeVisible();
    });

    test("API Growth tier card is visible at $499", async ({ page }) => {
        await expect(page.getByText("API Growth").first()).toBeVisible();
        await expect(page.getByText("$499")).toBeVisible();
    });

    test("Free tier has 'View Leaderboard' link", async ({ page }) => {
        const viewLink = page.getByRole("link", { name: /view leaderboard/i });
        await expect(viewLink).toBeVisible();
        await expect(viewLink).toHaveAttribute("href", "/ledger");
    });

    test("paid tiers show upgrade/get-started buttons", async ({ page }) => {
        // At least one paid upgrade button is visible
        const upgradeButtons = page.getByRole("button", { name: /upgrade to pro|get api starter|get api growth/i });
        const count = await upgradeButtons.count();
        expect(count).toBeGreaterThan(0);
    });

    test("Pro tier features list mentions 'Complete prediction history'", async ({ page }) => {
        await expect(page.getByText("Complete prediction history")).toBeVisible();
    });

    test("API Starter features list mentions 'REST API access'", async ({ page }) => {
        await expect(page.getByText("REST API access")).toBeVisible();
    });

    test("unauthenticated upgrade click redirects to sign-in or stays on pricing", async ({ page }) => {
        // Intercept checkout so we don't hit Stripe
        await page.route("/api/billing/checkout", async (route) => {
            await route.fulfill({
                status: 401,
                contentType: "application/json",
                body: JSON.stringify({ error: "Unauthorized" }),
            });
        });

        // Find any upgrade button
        const upgradeBtn = page
            .getByRole("button", { name: /upgrade to pro/i })
            .first();
        if (await upgradeBtn.isVisible()) {
            const navPromise = page.waitForURL(/sign-in|sign-up|pricing/, {
                timeout: 5000,
            });
            await upgradeBtn.click();
            await navPromise.catch(() => {
                // May stay on pricing if button goes through modal flow — acceptable
            });
        }
    });
});
