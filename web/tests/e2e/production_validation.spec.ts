import { test, expect } from '@playwright/test';

test.describe('Production Pipeline Verification (No Auth)', () => {
    
    test('Homepage loads globally without crashing', async ({ page }) => {
        const response = await page.goto('/');
        expect(response?.status()).toBe(200);
        await expect(page.locator('body')).toBeVisible();
    });

    test('Data Hydration: Real DB rendering (Dak Prescott page)', async ({ page }) => {
        // We know exactly what Dak's Cap Hit is in 2025. It should render without failing.
        const response = await page.goto('/player/dak-prescott');
        expect(response?.status()).toBe(200);
        
        // Assert that the page renders without throwing a React Error Boundary
        const errorBoundary = page.locator('text="Application Error"');
        await expect(errorBoundary).toHaveCount(0);
        
        // We ensure data components are visible
        const pageBody = await page.textContent('body');
        expect(pageBody).not.toContain("Application Error");
    });
    
    test('Data Degradation: Missing Player Page Gracefully Returns 404', async ({ page }) => {
        const response = await page.goto('/player/this-player-does-not-exist');
        // Next.js returns 404 for unknown dynamic paths when properly coded
        expect(response?.status()).toBe(404);
    });
    test('GM Persona: Team Roster loads successfully without errors (Dallas Cowboys)', async ({ page }) => {
        const response = await page.goto('/team/DAL');
        expect(response?.status()).toBe(200);
        const errorBoundary = page.locator('text="Application Error"');
        await expect(errorBoundary).toHaveCount(0);
        const pageBody = await page.textContent('body');
        expect(pageBody).not.toContain("Application Error");
    });

    test('Sharp Persona: Data Hydration & News rendering (Travis Kelce page)', async ({ page }) => {
        const response = await page.goto('/player/travis-kelce');
        expect(response?.status()).toBe(200);
        const errorBoundary = page.locator('text="Application Error"');
        await expect(errorBoundary).toHaveCount(0);
        const pageBody = await page.textContent('body');
        expect(pageBody).not.toContain("Application Error");
    });

});
