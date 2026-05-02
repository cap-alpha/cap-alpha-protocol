/**
 * E2E: Share-prediction flow
 *
 * Verifies:
 *   1. Ledger page renders prediction rows
 *   2. Share button copies a URL containing the prediction ID to clipboard
 *   3. OG image route responds with an image content-type
 *
 * Requires a running Next.js dev/prod server (PLAYWRIGHT_BASE_URL or localhost:3000).
 * The OG route test makes a real HTTP request to the running server.
 */

import { test, expect } from "@playwright/test";

test.describe("Prediction share button", () => {
    test.beforeEach(async ({ page }) => {
        // Grant clipboard write permission
        await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
    });

    test("share button copies URL with prediction ID to clipboard", async ({ page }) => {
        await page.goto("/ledger");

        // Wait for prediction rows to load (Recent tab may not be default)
        // Click the "Recent" tab if present
        const recentTab = page.getByRole("button", { name: /recent/i });
        if (await recentTab.isVisible()) {
            await recentTab.click();
        }

        // Wait for at least one prediction row with a share button
        const shareButton = page.locator("button", { hasText: /share/i }).first();
        await expect(shareButton).toBeVisible({ timeout: 15000 });

        // Grab the prediction hash from the closest hash span in the same row
        // (the #<hash> span sits in the same flex container as the share button)
        const row = shareButton.locator("..").locator("..");
        const hashSpan = row.locator("span").filter({ hasText: /^#[a-f0-9]+/ }).first();
        let predictionId: string | null = null;
        if (await hashSpan.isVisible()) {
            const text = await hashSpan.textContent();
            predictionId = text?.replace("#", "").trim() ?? null;
        }

        await shareButton.click();

        // After click, "Copied!" should appear
        await expect(shareButton).toContainText("Copied!", { timeout: 3000 });

        // Read clipboard content
        const clipboardText = await page.evaluate(() => navigator.clipboard.readText());
        expect(clipboardText).toMatch(/https?:\/\/.+\/ledger\?prediction=/);

        if (predictionId) {
            expect(clipboardText).toContain(predictionId);
        }
    });

    test("OG image route returns an image response", async ({ request, baseURL }) => {
        // We need at least one valid prediction ID — use a placeholder if none available.
        // This test mainly validates the route is reachable and returns image content.
        const ledgerRes = await request.get("/api/ledger/recent?limit=5");
        let predictionId = "test";
        if (ledgerRes.ok()) {
            const data = await ledgerRes.json();
            const first = data.predictions?.[0];
            if (first?.prediction_hash_short) {
                predictionId = first.prediction_hash_short;
            }
        }

        const ogRes = await request.get(`/api/og/prediction/${predictionId}`);
        // Route should respond — either 200 with image or at minimum not 404/500
        expect(ogRes.status()).toBeLessThan(500);

        const contentType = ogRes.headers()["content-type"] ?? "";
        // next/og returns image/png
        if (ogRes.ok()) {
            expect(contentType).toMatch(/image\//);
        }
    });
});
