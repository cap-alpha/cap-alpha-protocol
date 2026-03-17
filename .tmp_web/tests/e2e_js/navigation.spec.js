"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const test_1 = require("@playwright/test");
test_1.test.describe('Core Navigation & Layout', () => {
    (0, test_1.test)('Homepage Loads with Correct Branding', async ({ page }) => {
        // Navigate to home
        await page.goto('/');
        // Verify Title
        await (0, test_1.expect)(page).toHaveTitle(/Cap Alpha Protocol/);
        // Verify Header Branding
        const header = page.getByRole('heading', { level: 1 });
        await (0, test_1.expect)(header).toContainText('CAP ALPHA PROTOCOL');
        await (0, test_1.expect)(header).toContainText('EXECUTIVE SUITE');
    });
    (0, test_1.test)('KPI Cards Render Correctly', async ({ page }) => {
        await page.goto('/');
        // Verify presence of 4 KPI cards
        const kpiCards = page.locator('.grid.gap-4 .bg-card');
        await (0, test_1.expect)(kpiCards).toHaveCount(4);
        // Verify specific KPI labels
        await (0, test_1.expect)(page.getByText('Total Cap Liabilities')).toBeVisible();
        await (0, test_1.expect)(page.getByText('Risk Exposure')).toBeVisible();
        await (0, test_1.expect)(page.getByText('Active Contracts')).toBeVisible();
        await (0, test_1.expect)(page.getByText('Market Efficiency')).toBeVisible();
    });
    (0, test_1.test)('Tab Navigation Works', async ({ page }) => {
        await page.goto('/');
        // Default Tab should remain "Portfolio Library"
        const portfolioTab = page.getByRole('tab', { name: 'Portfolio Library' });
        await (0, test_1.expect)(portfolioTab).toHaveAttribute('data-state', 'active');
        // Switch to Data Grid
        const gridTab = page.getByRole('tab', { name: 'Data Grid' });
        await gridTab.click();
        await (0, test_1.expect)(gridTab).toHaveAttribute('data-state', 'active');
        // Switch to Trade Machine (War Room)
        const tradeTab = page.getByRole('tab', { name: 'The War Room (Trade)' });
        await tradeTab.click();
        await (0, test_1.expect)(tradeTab).toHaveAttribute('data-state', 'active');
    });
    (0, test_1.test)('Auth Elements for Signed Out User', async ({ page }) => {
        await page.goto('/');
        // Verify "Sign In" button is visible
        const signInBtn = page.getByRole('button', { name: 'Sign In' });
        await (0, test_1.expect)(signInBtn).toBeVisible();
        // Verify "Market: Open" badge
        await (0, test_1.expect)(page.getByText('MARKET: OPEN')).toBeVisible();
    });
});
