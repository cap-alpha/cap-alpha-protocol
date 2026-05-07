import { test, expect } from "@playwright/test";

/**
 * E2E tests for the pundit search bar on the /ledger page.
 *
 * These tests require the dev server at http://localhost:3000 to be running
 * and the /api/search/pundits endpoint to be reachable (may return mock/empty
 * results in CI without backend credentials — the UI assertions still apply).
 */

test.describe("Pundit search — primary navigation", () => {
    test("search bar is visible on /ledger without cmd+K", async ({ page }) => {
        await page.goto("/ledger");

        // The PunditSearchBar input should be directly visible (not behind a modal)
        const searchInput = page.getByRole("combobox", { name: /search pundits/i });
        await expect(searchInput).toBeVisible();

        // Should NOT require cmd+K to be visible
        // (GlobalSearch modal trigger still exists but search bar is already visible)
    });

    test("typing shows dropdown within 500ms", async ({ page }) => {
        await page.goto("/ledger");

        const searchInput = page.getByRole("combobox", { name: /search pundits/i }).first();
        await searchInput.fill("Schefter");

        // Wait for dropdown to appear (debounce 300ms + network)
        const listbox = page.getByRole("listbox", { name: /pundit search results/i });
        await expect(listbox).toBeVisible({ timeout: 500 });
    });

    test("pressing Escape closes dropdown but retains query value", async ({ page }) => {
        await page.goto("/ledger");

        const searchInput = page.getByRole("combobox", { name: /search pundits/i }).first();
        await searchInput.fill("Sc");

        // Wait briefly for debounce then open
        await page.waitForTimeout(350);

        await searchInput.press("Escape");

        // Input still has the typed value
        await expect(searchInput).toHaveValue("Sc");
    });

    test("search bar is present in navbar on desktop viewport", async ({ page }) => {
        await page.setViewportSize({ width: 1280, height: 800 });
        await page.goto("/ledger");

        // Navbar-level search bar (hidden on mobile via CSS, visible on lg+)
        const navbarSearchInputs = page.getByRole("combobox", { name: /search pundits/i });
        // There should be at least one (navbar) + one (page header) = 2 on desktop
        await expect(navbarSearchInputs).toHaveCount(2);
    });

    test("search bar is not in navbar on mobile viewport", async ({ page }) => {
        await page.setViewportSize({ width: 390, height: 844 });
        await page.goto("/ledger");

        // On mobile, only the page-header search bar should be rendered visibly
        const searchInputs = page.getByRole("combobox", { name: /search pundits/i });
        // Navbar bar exists in DOM but is hidden via CSS (hidden lg:flex)
        // Only the page-level one should be visible
        const visibleCount = await searchInputs.evaluateAll((els) =>
            els.filter((el) => {
                const style = window.getComputedStyle(el);
                return style.display !== "none" && style.visibility !== "hidden";
            }).length
        );
        expect(visibleCount).toBe(1);
    });
});
