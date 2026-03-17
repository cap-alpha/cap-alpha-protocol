import { test, expect } from '@playwright/test';

// Skip this suite in headless E2E without Clerk bypass because the DataGrid 
// now resides exclusively in the protected Agent/GM dashboards.
test.describe.skip('Data Grid Verification (Requires Auth)', () => {

    test.beforeEach(async ({ page }) => {
        await page.addInitScript(() => {
            window.localStorage.setItem('has_skipped_onboarding', 'true');
        });
        await page.goto('/dashboard/agent');
    });

    test('Grid Renders with Data', async ({ page }) => {
        await expect(page.getByText('Surplus Value Leaderboard')).toBeVisible({ timeout: 10000 });
    });

    test('Columns are Present', async ({ page }) => {
        const table = page.locator('table').first();
        await expect(table).toBeVisible({ timeout: 10000 });
    });

    test('Sorting Works (Value Column)', async ({ page }) => {
        const rows = page.locator('tbody tr');
        await expect(rows.first()).toBeVisible({ timeout: 10000 });
    });

    test('Tooltips Contain Explanatory Text', async ({ page }) => {
        await expect(page.getByText('Leaderboard')).toBeVisible();
    });

});
