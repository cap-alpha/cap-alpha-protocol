import { test, expect } from '@playwright/test';

test.describe('Core Navigation & Layout', () => {

    test.beforeEach(async ({ page }) => {
        await page.addInitScript(() => {
            window.localStorage.setItem('has_skipped_onboarding', 'true');
        });
    });

    test('Homepage Loads with Correct Branding', async ({ page }) => {
        // Navigate to home
        await page.goto('/dashboard');

        // Verify Title
        await expect(page).toHaveTitle(/Cap Alpha Protocol/);

        // Verify Header Branding
        const header = page.getByRole('heading', { level: 1 });
        await expect(header).toContainText('CAP ALPHA PROTOCOL');
        await expect(header).toContainText('EXECUTIVE SUITE');
    });

    test('KPI Cards Render Correctly', async ({ page }) => {
        await page.goto('/dashboard');

        // Verify presence of 5 KPI cards
        const kpiCards = page.locator('.grid.gap-4 .bg-card');
        await expect(kpiCards).toHaveCount(5);

        // Verify specific KPI labels
        await expect(page.getByText('Total Cap Liabilities')).toBeVisible();
        await expect(page.getByText('Risk Exposure')).toBeVisible();
        await expect(page.getByText('Active Contracts')).toBeVisible();
        await expect(page.getByText('Market Efficiency')).toBeVisible();
    });

    test('Tab Navigation Works', async ({ page }) => {
        await page.goto('/dashboard');

        // Default Tab should remain "Portfolio Library"
        const portfolioTab = page.getByRole('tab', { name: 'Portfolio Library' });
        await expect(portfolioTab).toHaveAttribute('data-state', 'active');

        // Switch to Data Grid
        const gridTab = page.getByRole('tab', { name: 'Data Grid' });
        await gridTab.click();
        await expect(gridTab).toHaveAttribute('data-state', 'active');

        // Switch to Trade Machine (War Room)
        const tradeTab = page.getByRole('tab', { name: 'The War Room (Trade)' });
        await tradeTab.click();
        await expect(tradeTab).toHaveAttribute('data-state', 'active');
    });

    test('Auth Elements for Signed Out User', async ({ page }) => {
        await page.goto('/dashboard');

        // Switch to Trade tab to expose the Paywall component
        await page.getByRole('tab', { name: 'The War Room (Trade)' }).click();

        // Verify Paywall blocks access
        await expect(page.getByText('PREMIUM INTELLIGENCE REQUIRED')).toBeVisible();

        // Verify "Unlock The War Room" CTA exists
        const signInBtn = page.getByRole('button', { name: /Unlock/i });
        await expect(signInBtn).toBeVisible();

        // Verify "Market: Open" badge still exists globally
        await expect(page.getByText('MARKET: OPEN')).toBeVisible();
    });

});
