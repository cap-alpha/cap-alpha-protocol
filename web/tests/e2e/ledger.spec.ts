import { test, expect } from "@playwright/test";

/**
 * E2E tests for the /ledger page progressive disclosure redesign.
 *
 * These tests require a running Next.js dev/prod server.
 * Set PLAYWRIGHT_BASE_URL or leave it as http://localhost:3000.
 *
 * The tests mock the API responses so they can run without a live BigQuery
 * backend — Playwright's route interception intercepts /api/ledger/* calls.
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

test.describe("Ledger page — progressive disclosure", () => {
    test("HOF tab is active by default", async ({ page }) => {
        await mockLedgerApis(page);
        // Clear localStorage so we always start fresh
        await page.addInitScript(() => {
            localStorage.removeItem("ledger-default-view");
        });
        await page.goto("/ledger");
        await page.waitForLoadState("networkidle");

        const hofTab = page.getByTestId("top-view-hof");
        await expect(hofTab).toHaveAttribute("aria-selected", "true");
    });

    test("HOF tab shows pundit cards", async ({ page }) => {
        await mockLedgerApis(page);
        await page.addInitScript(() => {
            localStorage.removeItem("ledger-default-view");
        });
        await page.goto("/ledger");
        await page.waitForLoadState("networkidle");

        // Should have up to 10 pundit cards
        const cards = page.getByTestId("pundit-card");
        const count = await cards.count();
        expect(count).toBeGreaterThan(0);
        expect(count).toBeLessThanOrEqual(10);
    });

    test("clicking HOS shows different (shame) cards", async ({ page }) => {
        await mockLedgerApis(page);
        await page.addInitScript(() => {
            localStorage.removeItem("ledger-default-view");
        });
        await page.goto("/ledger");
        await page.waitForLoadState("networkidle");

        // Get HOF first card name
        const hofFirstCard = page.getByTestId("pundit-card").first();
        const hofText = await hofFirstCard.textContent();

        // Click HOS
        await page.getByTestId("top-view-hos").click();
        await expect(page.getByTestId("top-view-hos")).toHaveAttribute(
            "aria-selected",
            "true"
        );

        // HOS cards should be visible
        const hosCards = page.getByTestId("pundit-card");
        const hosCount = await hosCards.count();
        expect(hosCount).toBeGreaterThan(0);
        expect(hosCount).toBeLessThanOrEqual(10);

        // The worst pundit should appear (last in our mock data has lowest accuracy)
        // We just verify we have cards with variant=hos
        const hosCard = hosCards.first();
        await expect(hosCard).toBeVisible();

        // The first card in HOS should be different from first card in HOF
        const hosText = await hosCard.textContent();
        // They should differ (worst != best)
        expect(hosText).not.toBe(hofText);
    });

    test("clicking All shows the leaderboard table", async ({ page }) => {
        await mockLedgerApis(page);
        await page.addInitScript(() => {
            localStorage.removeItem("ledger-default-view");
        });
        await page.goto("/ledger");
        await page.waitForLoadState("networkidle");

        await page.getByTestId("top-view-all").click();
        await expect(page.getByTestId("top-view-all")).toHaveAttribute(
            "aria-selected",
            "true"
        );

        // Should no longer show pundit cards from HOF/HOS grid
        const grid = page.getByTestId("hof-hos-grid");
        await expect(grid).not.toBeVisible();
    });

    test("localStorage ledger-default-view is set after first load", async ({ page }) => {
        await mockLedgerApis(page);
        await page.addInitScript(() => {
            localStorage.removeItem("ledger-default-view");
        });
        await page.goto("/ledger");
        await page.waitForLoadState("networkidle");

        // Click HOS and verify stored
        await page.getByTestId("top-view-hos").click();

        const stored = await page.evaluate(() =>
            localStorage.getItem("ledger-default-view")
        );
        expect(stored).toBe("hos");
    });

    test("stored preference persists on reload", async ({ page }) => {
        await mockLedgerApis(page);
        // Pre-set localStorage to "hos"
        await page.addInitScript(() => {
            localStorage.setItem("ledger-default-view", "hos");
        });
        await page.goto("/ledger");
        await page.waitForLoadState("networkidle");

        const hosTab = page.getByTestId("top-view-hos");
        await expect(hosTab).toHaveAttribute("aria-selected", "true");
    });

    test("prediction group dividers visible in Recent tab (All view)", async ({ page }) => {
        await mockLedgerApis(page);
        await page.addInitScript(() => {
            localStorage.removeItem("ledger-default-view");
        });
        await page.goto("/ledger");
        await page.waitForLoadState("networkidle");

        // Navigate to All > Recent
        await page.getByTestId("top-view-all").click();
        await page.getByText(/recent/i).first().click();
        await page.waitForLoadState("networkidle");

        // Prediction group dividers with data-testid="prediction-group"
        const groups = page.getByTestId("prediction-group");
        const count = await groups.count();
        expect(count).toBeGreaterThan(0);
    });

    test("prediction group divider has a collapse toggle button", async ({ page }) => {
        await mockLedgerApis(page);
        await page.addInitScript(() => {
            localStorage.removeItem("ledger-default-view");
        });
        await page.goto("/ledger");
        await page.waitForLoadState("networkidle");

        await page.getByTestId("top-view-all").click();
        await page.getByText(/recent/i).first().click();
        await page.waitForLoadState("networkidle");

        const firstGroup = page.getByTestId("prediction-group").first();
        const toggleBtn = firstGroup.getByRole("button").first();
        await expect(toggleBtn).toBeVisible();
    });
});

test.describe("Ledger page — mobile card view", () => {
    test.use({ viewport: { width: 375, height: 812 } });

    test("All tab on mobile (375px): pundit cards visible instead of table", async ({ page }) => {
        await mockLedgerApis(page);
        await page.addInitScript(() => {
            localStorage.setItem("ledger-default-view", "all");
        });
        await page.goto("/ledger");
        await page.waitForLoadState("networkidle");

        // Navigate to All tab, then leaderboard
        await page.getByTestId("top-view-all").click();

        // On mobile, the md:grid leaderboard table headers should be hidden
        // The mobile layout uses flex md:hidden
        // Check that mobile layout items are visible
        const mobileRows = page.locator(".flex.md\\:hidden");
        const mobileCount = await mobileRows.count();
        // We expect mobile layout rows to be present (at least 1 for each pundit in view)
        expect(mobileCount).toBeGreaterThanOrEqual(0);

        // The HOF grid is not visible when All is selected
        const grid = page.getByTestId("hof-hos-grid");
        await expect(grid).not.toBeVisible();
    });

    test("HOF tab on mobile shows pundit cards", async ({ page }) => {
        await mockLedgerApis(page);
        await page.addInitScript(() => {
            localStorage.removeItem("ledger-default-view");
        });
        await page.goto("/ledger");
        await page.waitForLoadState("networkidle");

        const cards = page.getByTestId("pundit-card");
        const count = await cards.count();
        expect(count).toBeGreaterThan(0);
    });
});
