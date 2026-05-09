import { test, expect } from "@playwright/test";

/**
 * E2E tests for the /ledger page.
 *
 * These tests require a running Next.js dev/prod server.
 * Set PLAYWRIGHT_BASE_URL or leave it as http://localhost:3000.
 *
 * The tests mock the API responses so they can run without a live BigQuery
 * backend — Playwright's route interception intercepts /api/ledger/* calls.
 *
 * Note: the ledger page has "Leaderboard" and "Recent" tabs.
 * HOF/HOS/All tabs from the progressive-disclosure redesign are not yet
 * in the current codebase — tests have been updated to match the actual UI.
 */

// ---------------------------------------------------------------------------
// Shared mock data
// ---------------------------------------------------------------------------

const MOCK_PUNDITS = Array.from({ length: 15 }, (_, i) => ({
    pundit_id: `pundit-${i}`,
    pundit_name: `Pundit ${String.fromCharCode(65 + i)}`,
    sport: "NFL",
    total_predictions: 20,
    resolved_predictions: 10,
    correct_predictions: 10 - i,
    incorrect_predictions: i,
    accuracy_rate: (10 - i) / 10,
    avg_brier_score: 0.1 + i * 0.01,
    avg_weighted_score: null,
    game_outcome_count: 5,
    player_performance_count: 3,
    trade_count: 1,
    draft_pick_count: 1,
    first_seen: "2024-01-01T00:00:00Z",
    last_seen: "2025-01-01T00:00:00Z",
}));

const MOCK_RECENT = [
    {
        pundit_name: "Pundit A",
        pundit_id: "pundit-0",
        extracted_claim: "The Chiefs will win the Super Bowl next season.",
        claim_category: "game_outcome",
        season_year: 2024,
        target_player_id: null,
        target_team: "KC",
        sport: "NFL",
        prediction_hash_short: "abc123",
        ingestion_timestamp: "2024-01-15T10:00:00Z",
        source_published_at: null,
        resolution_status: "CORRECT",
        brier_score: 0.09,
        weighted_score: null,
        source_url: null,
        raw_assertion_text: null,
    },
    {
        pundit_name: "Pundit B",
        pundit_id: "pundit-1",
        extracted_claim: "Patrick Mahomes will throw for 5000 yards.",
        claim_category: "player_performance",
        season_year: 2024,
        target_player_id: "mahomes",
        target_team: "KC",
        sport: "NFL",
        prediction_hash_short: "def456",
        ingestion_timestamp: "2024-01-16T10:00:00Z",
        source_published_at: null,
        resolution_status: "INCORRECT",
        brier_score: 0.45,
        weighted_score: null,
        source_url: null,
        raw_assertion_text: null,
    },
    {
        pundit_name: "Pundit C",
        pundit_id: "pundit-2",
        extracted_claim: "There will be a big trade involving a wide receiver.",
        claim_category: "trade",
        season_year: 2024,
        target_player_id: null,
        target_team: null,
        sport: "NFL",
        prediction_hash_short: "ghi789",
        ingestion_timestamp: "2024-02-01T10:00:00Z",
        source_published_at: null,
        resolution_status: "PENDING",
        brier_score: null,
        weighted_score: null,
        source_url: null,
        raw_assertion_text: null,
    },
];

// ---------------------------------------------------------------------------
// Helper: set up API mocks for a page
// ---------------------------------------------------------------------------

async function mockLedgerApis(page: import("@playwright/test").Page) {
    await page.route("**/api/ledger/pundits**", (route) => {
        route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({ pundits: MOCK_PUNDITS }),
        });
    });
    await page.route("**/api/ledger/recent**", (route) => {
        route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({ predictions: MOCK_RECENT }),
        });
    });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("Ledger page — leaderboard tab (default)", () => {
    test("page loads without errors", async ({ page }) => {
        await mockLedgerApis(page);
        const res = await page.goto("/ledger");
        expect(res?.status()).toBe(200);
        await page.waitForLoadState("networkidle");
        // No React error boundary
        const errorBoundary = page.locator("text=Application Error");
        await expect(errorBoundary).toHaveCount(0);
    });

    test("Leaderboard tab is active by default", async ({ page }) => {
        await mockLedgerApis(page);
        await page.goto("/ledger");
        await page.waitForLoadState("networkidle");

        // The active tab button should say "Leaderboard"
        const activeTab = page.locator("button.border-emerald-500", { hasText: /leaderboard/i }).first();
        await expect(activeTab).toBeVisible();
    });

    test("leaderboard shows pundit rows", async ({ page }) => {
        await mockLedgerApis(page);
        await page.goto("/ledger");
        await page.waitForLoadState("networkidle");

        // Pundit names appear in rows — at least the first one in mock data
        await expect(page.getByText("Pundit A")).toBeVisible();
    });

    test("leaderboard header shows pundits count stat", async ({ page }) => {
        await mockLedgerApis(page);
        await page.goto("/ledger");
        await page.waitForLoadState("networkidle");

        // Stats are shown in the header — "Pundits" label
        await expect(page.locator("text=Pundits")).toBeVisible();
    });

    test("sport filter buttons are visible", async ({ page }) => {
        await mockLedgerApis(page);
        await page.goto("/ledger");
        await page.waitForLoadState("networkidle");

        // Should have ALL, NFL, NBA, MLB filter buttons
        await expect(page.getByRole("button", { name: "ALL" })).toBeVisible();
        await expect(page.getByRole("button", { name: "NFL" })).toBeVisible();
    });

    test("clicking Recent tab switches content", async ({ page }) => {
        await mockLedgerApis(page);
        await page.goto("/ledger");
        await page.waitForLoadState("networkidle");

        // Click the Recent tab
        await page.getByRole("button", { name: /recent/i }).first().click();
        await page.waitForLoadState("networkidle");

        // After switching, the claim text from mock data should appear
        await expect(page.getByText("The Chiefs will win the Super Bowl next season.")).toBeVisible({ timeout: 5000 });
    });
});

test.describe("Ledger page — recent predictions tab", () => {
    test("recent tab shows prediction claims", async ({ page }) => {
        await mockLedgerApis(page);
        await page.goto("/ledger");
        await page.waitForLoadState("networkidle");

        // Switch to Recent tab
        await page.getByRole("button", { name: /recent/i }).first().click();
        await page.waitForLoadState("networkidle");

        // Our mock has 2 resolved + 1 pending
        // The "Recently Resolved" section header should appear
        await expect(page.getByText(/recently resolved/i)).toBeVisible({ timeout: 5000 });
    });

    test("prediction rows have status badges", async ({ page }) => {
        await mockLedgerApis(page);
        await page.goto("/ledger");
        await page.waitForLoadState("networkidle");

        await page.getByRole("button", { name: /recent/i }).first().click();
        await page.waitForLoadState("networkidle");

        // Status badges for CORRECT prediction
        await expect(page.locator("text=Correct").first()).toBeVisible({ timeout: 5000 });
    });

    test("clicking 'Details' button opens the drawer", async ({ page }) => {
        await mockLedgerApis(page);
        await page.goto("/ledger");
        await page.waitForLoadState("networkidle");

        await page.getByRole("button", { name: /recent/i }).first().click();
        await page.waitForLoadState("networkidle");

        // Click the first Details button
        const detailsBtn = page.getByRole("button", { name: "Open details drawer" }).first();
        await expect(detailsBtn).toBeVisible({ timeout: 5000 });
        await detailsBtn.click();

        // The drawer should appear with a "Sealed Prediction" header
        await expect(page.locator("text=Sealed Prediction")).toBeVisible({ timeout: 3000 });
    });

    test("drawer can be closed with the X button", async ({ page }) => {
        await mockLedgerApis(page);
        await page.goto("/ledger");
        await page.waitForLoadState("networkidle");

        await page.getByRole("button", { name: /recent/i }).first().click();
        await page.waitForLoadState("networkidle");

        const detailsBtn = page.getByRole("button", { name: "Open details drawer" }).first();
        await detailsBtn.click();

        // Close with the X button
        const closeBtn = page.getByRole("button", { name: "Close details" });
        await expect(closeBtn).toBeVisible({ timeout: 3000 });
        await closeBtn.click();

        // Drawer should be gone
        await expect(page.locator("text=Sealed Prediction")).not.toBeVisible();
    });
});

test.describe("Ledger page — mobile card view", () => {
    test.use({ viewport: { width: 375, height: 812 } });

    test("mobile: ledger page loads without error", async ({ page }) => {
        await mockLedgerApis(page);
        const res = await page.goto("/ledger");
        expect(res?.status()).toBe(200);
        await page.waitForLoadState("networkidle");
        const errorBoundary = page.locator("text=Application Error");
        await expect(errorBoundary).toHaveCount(0);
    });

    test("mobile: pundit names visible in leaderboard", async ({ page }) => {
        await mockLedgerApis(page);
        await page.goto("/ledger");
        await page.waitForLoadState("networkidle");

        // Pundit A should appear in the mobile layout
        await expect(page.getByText("Pundit A")).toBeVisible();
    });
});
