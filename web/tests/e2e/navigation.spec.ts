import { test, expect } from '@playwright/test';

test.describe('Core Navigation & Layout', () => {

    test.beforeEach(async ({ page }) => {
        await page.addInitScript(() => {
            window.localStorage.setItem('has_skipped_onboarding', 'true');
        });
    });

    test('Homepage Loads with Correct Branding', async ({ page }) => {
        await page.goto('/');
        await expect(page).toHaveTitle(/Cap Alpha Protocol/);
        await expect(page.getByText('Choose your Persona.')).toBeVisible();
    });

    test('Public Fan Dashboard KPI Cards Render Correctly', async ({ page }) => {
        await page.goto('/dashboard/fan');
        await expect(page.getByText('Armchair')).toBeVisible();
        await expect(page.getByText('Franchise Power Rankings')).toBeVisible();
    });

    test('Tab Navigation to Fan Dashboard Works', async ({ page }) => {
        // Test redirecting from persona showcase to a public route
        await page.goto('/');
        const fanTab = page.getByText('The Armchair GM');
        await fanTab.click();
        await expect(page.getByRole('heading', { name: /Armchair GM/i }).first()).toBeVisible({ timeout: 10000 });
    });

    test('Auth Elements for Signed Out User (Sign In Redirect)', async ({ page }) => {
        await page.goto('/dashboard/gm');
        await expect(page).toHaveURL(/.*sign-in.*/);
    });

});
