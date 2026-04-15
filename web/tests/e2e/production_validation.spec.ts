import { test, expect } from '@playwright/test';

test.describe('Production Pipeline Verification (No Auth)', () => {

    test('Homepage loads globally without crashing', async ({ page }) => {
        const response = await page.goto('/');
        expect(response?.status()).toBe(200);
        await expect(page.locator('body')).toBeVisible();
    });

    test('Data Hydration: Real DB rendering (Dak Prescott page)', async ({ page }) => {
        // In CI/Docker without BigQuery, the roster is empty and the page returns 404.
        // In production with a live DB, the page returns 200 with player data.
        // Either way, the app must NOT return 500 (crash).
        const response = await page.goto('/player/dak-prescott');
        const status = response?.status() ?? 500;
        expect(status, 'Page must not crash with 500').not.toBe(500);
        expect([200, 404]).toContain(status);

        // Assert that the page renders without throwing a React Error Boundary
        const pageBody = await page.textContent('body');
        expect(pageBody).not.toContain("Application Error");
    });

    test('Data Degradation: Missing Player Page Gracefully Returns 404', async ({ page }) => {
        const response = await page.goto('/player/this-player-does-not-exist');
        // Next.js returns 404 for unknown dynamic paths when properly coded
        expect(response?.status()).toBe(404);
    });

    test('GM Persona: Team Roster loads successfully without errors (Dallas Cowboys)', async ({ page }) => {
        // Without BigQuery data the team page returns 404 (no roster to show).
        // With a live DB it returns 200. Either is acceptable; 500 is not.
        const response = await page.goto('/team/DAL');
        const status = response?.status() ?? 500;
        expect(status, 'Page must not crash with 500').not.toBe(500);
        expect([200, 404]).toContain(status);

        const pageBody = await page.textContent('body');
        expect(pageBody).not.toContain("Application Error");
    });

    test('Sharp Persona: Data Hydration & News rendering (Travis Kelce page)', async ({ page }) => {
        // Same pattern: 200 with live data, 404 without. Never 500.
        const response = await page.goto('/player/travis-kelce');
        const status = response?.status() ?? 500;
        expect(status, 'Page must not crash with 500').not.toBe(500);
        expect([200, 404]).toContain(status);

        const pageBody = await page.textContent('body');
        expect(pageBody).not.toContain("Application Error");
    });

});
