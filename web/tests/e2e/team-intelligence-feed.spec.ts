/**
 * Regression test: IntelligenceFeed panel wiring on team page (#739)
 *
 * After PR #703, the IntelligenceFeed panel fetches real BQ data via
 * getIntelligenceFeed() instead of a stub. This test guards against the panel
 * disappearing or silently rendering nothing (null/undefined) due to a broken
 * data fetch.
 *
 * Auth note: IntelligenceFeed wraps its content in Clerk <SignedIn> / <SignedOut>.
 * In the unauthenticated (signed-out) test environment, the panel renders a
 * paywall overlay — not the feed events themselves — so we assert the outer Card
 * is present rather than the feed rows.  The "signed-in" data path is exercised
 * by integration tests that run with a test Clerk session.
 *
 * E2E suite note: several unrelated visual-regression and ledger tests were already
 * failing before PR #703 landed (pre-existing flakes tracked in the [advisory]
 * E2E check). This spec is scoped to the team page only and should not be affected
 * by those flakes.
 */

import { test, expect } from '@playwright/test';

// Use a team that has BQ data; DAL is already exercised in production_validation.spec.ts
// KC is a high-profile team very likely to have non-empty data in any environment.
const TEST_TEAM_ID = 'KC';

test.describe('IntelligenceFeed panel — team page wiring (#739)', () => {

    test('team page renders without application error', async ({ page }) => {
        const response = await page.goto(`/team/${TEST_TEAM_ID}`);
        expect(response?.status()).toBe(200);

        // Ensure Next.js error boundary did not fire
        await expect(page.locator('text="Application Error"')).toHaveCount(0);
        const body = await page.textContent('body');
        expect(body).not.toContain('Application Error');
    });

    test('IntelligenceFeed panel is present in the DOM', async ({ page }) => {
        await page.goto(`/team/${TEST_TEAM_ID}`);

        // The panel's CardTitle text — present regardless of auth state.
        // If this locator is missing the entire IntelligenceFeed card was not rendered.
        const panelHeading = page.getByText('Cap Alpha Intelligence');
        await expect(panelHeading).toBeVisible({ timeout: 10_000 });

        // "Live Feed" badge is always rendered inside the card header
        const liveBadge = page.getByText('Live Feed');
        await expect(liveBadge).toBeVisible();
    });

    test('signed-out paywall overlay is rendered (auth gating is intact)', async ({ page }) => {
        await page.goto(`/team/${TEST_TEAM_ID}`);

        // When unauthenticated, Clerk <SignedOut> renders a paywall overlay.
        // This asserts auth gating is wired correctly (not silently stripped).
        const paywallHeading = page.getByText('PRO INTELLIGENCE REQUIRED');
        await expect(paywallHeading).toBeVisible({ timeout: 10_000 });
    });

    test('IntelligenceFeed panel does not render a React loading spinner as its only child', async ({ page }) => {
        await page.goto(`/team/${TEST_TEAM_ID}`);

        // Wait for hydration
        await page.waitForLoadState('networkidle');

        // The panel heading must be visible — meaning the component fully mounted
        await expect(page.getByText('Cap Alpha Intelligence')).toBeVisible({ timeout: 15_000 });

        // The animate-pulse skeleton divs must NOT be the only thing visible inside
        // the feed area when the page is fully loaded.  We check that at least the
        // paywall overlay OR a feed-related text node is present (not just spinners).
        const paywallOrFeedPresent = await page.evaluate(() => {
            const body = document.body.textContent ?? '';
            return (
                body.includes('PRO INTELLIGENCE REQUIRED') ||
                body.includes('No Intelligence Events') ||
                body.includes('Synthesized intelligence')
            );
        });
        expect(paywallOrFeedPresent).toBe(true);
    });

});
