import { test, expect } from "@playwright/test";

/**
 * E2E tests for ledger page navigation and filtering.
 *
 * Note: A dedicated PunditSearchBar combobox with aria-label="search pundits"
 * does not yet exist in the current codebase. These tests have been rewritten
 * to cover the sport-filter buttons that are present in the /ledger page,
 * which serve the primary filtering use case.
 *
 * When a pundit search bar is added, update these tests to cover that feature.
 */

test.describe("Ledger page — sport filter navigation", () => {
    test("sport filter buttons are visible on /ledger", async ({ page }) => {
        await page.goto("/ledger");
        await page.waitForLoadState("networkidle");

        // Sport filter: ALL, NFL, NBA, MLB
        const allBtn = page.getByRole("button", { name: "ALL" });
        await expect(allBtn).toBeVisible();

        const nflBtn = page.getByRole("button", { name: "NFL" });
        await expect(nflBtn).toBeVisible();
    });

    test("ALL filter is selected by default", async ({ page }) => {
        await page.goto("/ledger");
        await page.waitForLoadState("networkidle");

        // The ALL button should have the active styling (emerald accent)
        const allBtn = page.getByRole("button", { name: "ALL" });
        await expect(allBtn).toBeVisible();
        // Verify active styling via class (emerald border and text)
        await expect(allBtn).toHaveClass(/emerald/);
    });

    test("clicking NFL filter updates the page", async ({ page }) => {
        // Mock the API to avoid network issues
        await page.route("**/api/ledger/pundits**", (route) => {
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({ pundits: [] }),
            });
        });
        await page.route("**/api/ledger/recent**", (route) => {
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({ predictions: [] }),
            });
        });

        await page.goto("/ledger");
        await page.waitForLoadState("networkidle");

        const nflBtn = page.getByRole("button", { name: "NFL" });
        await nflBtn.click();

        // After clicking, NFL button should have active styling
        await expect(nflBtn).toHaveClass(/emerald/);
        // A note about filtering should appear
        await expect(page.getByText(/filtering leaderboard/i)).toBeVisible();
    });

    test("ledger page renders without crash at desktop viewport", async ({ page }) => {
        await page.setViewportSize({ width: 1280, height: 800 });
        await page.goto("/ledger");
        await page.waitForLoadState("networkidle");

        const body = page.locator("body");
        await expect(body).toBeVisible();
        const errorBoundary = page.locator("text=Application Error");
        await expect(errorBoundary).toHaveCount(0);
    });

    test("ledger page renders without crash at mobile viewport", async ({ page }) => {
        await page.setViewportSize({ width: 390, height: 844 });
        await page.goto("/ledger");
        await page.waitForLoadState("networkidle");

        const body = page.locator("body");
        await expect(body).toBeVisible();
        const errorBoundary = page.locator("text=Application Error");
        await expect(errorBoundary).toHaveCount(0);
    });
});
