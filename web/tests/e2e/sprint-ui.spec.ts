import { test, expect } from '@playwright/test';

test.describe('Fantasy Sync Activation Funnel', () => {
    test('User must authenticate to view the fantasy dashboard', async ({ page }) => {
        // Go to the new fantasy page
        await page.goto('/fantasy');

        // Default state: Should show the locked access UI (Clerk SignedOut state)
        await expect(page.locator('text=RESTRICTED ACCESS')).toBeVisible();
        await expect(page.locator('button', { hasText: 'Request Access Token' })).toBeVisible();
    });

    // Note for real E2E: Testing the authenticated state typically involves 
    // bypassing Clerk locally using a test JWT or Cypress tasks. 
    // For the sake of this mock UI test, we verify the locked gate functions correctly.
});

test.describe('Real Team Page Analytics', () => {
    test('Navigates and loads a valid team roster view', async ({ page }) => {
        // Go to a specific team (e.g. Arizona)
        await page.goto('/team/ARI');

        // Should show the title for the team page component
        await expect(page.locator('h1', { hasText: 'ARI' })).toBeVisible();

        // Should show the mock RAG feed
        await expect(page.locator('text=Cap Alpha Intelligence')).toBeVisible();

        // Should show Cap Liabilities
        await expect(page.locator('text=Total Cap Liabilities')).toBeVisible();
    });
});
