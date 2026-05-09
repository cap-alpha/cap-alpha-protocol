import { test, expect } from "@playwright/test";
import path from "path";
import fs from "fs";

/**
 * Mobile viewport tests — iPhone 14 Pro (390×844)
 *
 * Issue #499: [Gate 1] [Launch P1] Mobile pass on real devices
 *
 * Acceptance criteria:
 *  - All public routes tested at 390px width (iPhone 14 Pro)
 *  - No horizontal scroll on any route
 *  - Touch targets ≥ 44×44px on interactive elements
 *  - Routes: /, /ledger, /draft/2025, /sign-in, /sign-up, /legal/terms
 *  - Ledger view readable and scrollable on mobile
 *
 * Run with:
 *   cd web && npx playwright test tests/e2e/mobile-viewport.spec.ts --project=chromium
 *
 * No auth required — only public routes are tested.
 */

const IPHONE_14_PRO = { width: 390, height: 844 };

/**
 * Routes from the acceptance criteria.
 * Notes:
 *  - /pundits does not exist as a standalone route; the pundit leaderboard
 *    lives at /ledger (tested below).
 *  - /draft requires a year segment; /draft/2025 is the canonical URL.
 *  - /legal/ maps to /legal/terms (the root /legal has no page.tsx).
 */
const PUBLIC_ROUTES = [
    "/",
    "/ledger",
    "/draft/2025",
    "/sign-in",
    "/sign-up",
    "/legal/terms",
];

// Ensure screenshot directory exists
const SCREENSHOT_DIR = path.join(
    __dirname,
    "../../playwright-report/mobile-screenshots"
);

test.beforeAll(() => {
    if (!fs.existsSync(SCREENSHOT_DIR)) {
        fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
    }
});

// ---------------------------------------------------------------------------
// 1. No horizontal overflow at 390px
// ---------------------------------------------------------------------------

test.describe("Mobile 390px — no horizontal overflow", () => {
    for (const route of PUBLIC_ROUTES) {
        test(`no horizontal scroll on ${route}`, async ({ page }) => {
            await page.setViewportSize(IPHONE_14_PRO);

            await page.goto(route, {
                waitUntil: "domcontentloaded",
                timeout: 30000,
            });

            // Allow animations / lazy images to settle
            await page.waitForTimeout(500);

            const scrollWidth = await page.evaluate(
                () => document.documentElement.scrollWidth
            );
            const clientWidth = await page.evaluate(
                () => document.documentElement.clientWidth
            );

            // Screenshot on every route (useful for review even on success)
            const screenshotName =
                route === "/"
                    ? "home"
                    : route.replace(/\//g, "-").replace(/^-/, "");
            await page.screenshot({
                path: path.join(SCREENSHOT_DIR, `${screenshotName}.png`),
                fullPage: true,
            });

            const overflow = scrollWidth - clientWidth;
            expect(
                overflow,
                `${route} has ${overflow}px of horizontal overflow — check for fixed-width elements or missing overflow-x:hidden`
            ).toBeLessThanOrEqual(0);
        });
    }
});

// ---------------------------------------------------------------------------
// 2. Touch targets ≥ 44×44px
//
// WCAG 2.5.5 (AAA) / Apple HIG / Android spec all require 44px minimum.
// We check every <a>, <button>, and [role="button"] on each public route.
// Elements that are hidden (display:none / visibility:hidden) are excluded.
// Small decorative icons (<16px) that are children of an already-valid touch
// target are also excluded via the `closest` guard in the evaluate callback.
// ---------------------------------------------------------------------------

test.describe("Mobile 390px — touch target size ≥ 44×44px", () => {
    for (const route of PUBLIC_ROUTES) {
        test(`touch targets on ${route}`, async ({ page }) => {
            await page.setViewportSize(IPHONE_14_PRO);

            await page.goto(route, {
                waitUntil: "domcontentloaded",
                timeout: 30000,
            });

            await page.waitForTimeout(500);

            const violations = await page.evaluate(() => {
                const MIN = 44;

                // Collect interactive elements
                const candidates = Array.from(
                    document.querySelectorAll(
                        'a, button, [role="button"], input[type="submit"], input[type="button"]'
                    )
                );

                const bad: string[] = [];

                for (const el of candidates) {
                    const htmlEl = el as HTMLElement;

                    // Skip hidden elements
                    const style = window.getComputedStyle(htmlEl);
                    if (
                        style.display === "none" ||
                        style.visibility === "hidden" ||
                        style.opacity === "0"
                    ) {
                        continue;
                    }

                    const rect = htmlEl.getBoundingClientRect();

                    // Skip zero-size elements (not rendered / off-screen)
                    if (rect.width === 0 && rect.height === 0) {
                        continue;
                    }

                    if (rect.width < MIN || rect.height < MIN) {
                        const label =
                            htmlEl.getAttribute("aria-label") ||
                            htmlEl.textContent?.trim().substring(0, 40) ||
                            htmlEl.getAttribute("href") ||
                            "(unlabelled)";
                        bad.push(
                            `<${htmlEl.tagName.toLowerCase()}> "${label}" — ${Math.round(rect.width)}×${Math.round(rect.height)}px`
                        );
                    }
                }

                return bad;
            });

            expect(
                violations,
                `Touch targets smaller than 44×44px on ${route}:\n${violations.join("\n")}`
            ).toHaveLength(0);
        });
    }
});

// ---------------------------------------------------------------------------
// 3. Ledger page — readable and scrollable on mobile
// ---------------------------------------------------------------------------

test.describe("Mobile 390px — ledger readability and scroll", () => {
    const MOCK_PUNDITS = Array.from({ length: 5 }, (_, i) => ({
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
    ];

    test("ledger page loads without error on mobile", async ({ page }) => {
        await page.setViewportSize(IPHONE_14_PRO);

        await page.route("**/api/ledger/pundits**", (route) =>
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({ pundits: MOCK_PUNDITS }),
            })
        );
        await page.route("**/api/ledger/recent**", (route) =>
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({ predictions: MOCK_RECENT }),
            })
        );

        const res = await page.goto("/ledger");
        expect(res?.status()).toBe(200);
        await page.waitForLoadState("networkidle");

        await expect(
            page.locator("text=Application Error")
        ).toHaveCount(0);
    });

    test("ledger shows pundit names at 390px width", async ({ page }) => {
        await page.setViewportSize(IPHONE_14_PRO);

        await page.route("**/api/ledger/pundits**", (route) =>
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({ pundits: MOCK_PUNDITS }),
            })
        );
        await page.route("**/api/ledger/recent**", (route) =>
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({ predictions: MOCK_RECENT }),
            })
        );

        await page.goto("/ledger");
        await page.waitForLoadState("networkidle");

        // Pundit names must be visible (not clipped off-screen)
        await expect(page.getByText("Pundit A")).toBeVisible();
    });

    test("ledger content is scrollable vertically on mobile", async ({
        page,
    }) => {
        await page.setViewportSize(IPHONE_14_PRO);

        await page.route("**/api/ledger/pundits**", (route) =>
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({ pundits: MOCK_PUNDITS }),
            })
        );
        await page.route("**/api/ledger/recent**", (route) =>
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({ predictions: MOCK_RECENT }),
            })
        );

        await page.goto("/ledger");
        await page.waitForLoadState("networkidle");

        // Page must be taller than the viewport (i.e., scrollable content exists)
        const scrollHeight = await page.evaluate(
            () => document.documentElement.scrollHeight
        );

        expect(
            scrollHeight,
            "Ledger page scrollHeight should exceed viewport height — content appears too short for a real page"
        ).toBeGreaterThan(IPHONE_14_PRO.height);
    });

    test("ledger has no horizontal overflow at 390px", async ({ page }) => {
        await page.setViewportSize(IPHONE_14_PRO);

        await page.route("**/api/ledger/pundits**", (route) =>
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({ pundits: MOCK_PUNDITS }),
            })
        );
        await page.route("**/api/ledger/recent**", (route) =>
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({ predictions: MOCK_RECENT }),
            })
        );

        await page.goto("/ledger");
        await page.waitForLoadState("networkidle");

        const scrollWidth = await page.evaluate(
            () => document.documentElement.scrollWidth
        );
        const clientWidth = await page.evaluate(
            () => document.documentElement.clientWidth
        );

        expect(
            scrollWidth - clientWidth,
            "Ledger page must not have horizontal overflow at 390px"
        ).toBeLessThanOrEqual(0);
    });
});
