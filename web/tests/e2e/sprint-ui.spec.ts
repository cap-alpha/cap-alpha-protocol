import { test, expect } from '@playwright/test';

test.describe('Paywall & Activation Funnel', () => {
    test('User must authenticate to view the fantasy dashboard', async ({ page }) => {
        // Go to the new fantasy page
        await page.goto('/fantasy');

        // Default state: Should show the locked access UI (Clerk SignedOut state)
        await expect(page.getByRole('heading', { name: /RESTRICTED ACCESS/i })).toBeVisible();
        await expect(page.getByRole('button', { name: /Request Access Token/i })).toBeVisible();
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

test.describe('Player Detail View UX & Data Science Features', () => {
    test('Loads the Data Science B.L.U.F. Executive Summary and handles the Cut Calculator toggle', async ({ page }) => {
        // Navigate to a highly paid player to ensure the detail view populates
        await page.goto('/player/Kyler%20Murray');

        // 1. Assert the Data Science B.L.U.F. summary is present
        await expect(page.getByRole('heading', { name: /Executive Summary/i })).toBeVisible();

        // 2. Validate the Cut Calculator (Action Panel)
        const postJuneToggle = page.locator('button[role="switch"]');
        await expect(postJuneToggle).toBeVisible();

        // Assert initial state is Pre-June 1 (toggle off)
        await expect(postJuneToggle).not.toHaveAttribute('aria-checked', 'true');

        // Ensure standard numbers show before toggle (Cap hit, Savings)
        await expect(page.locator('text=Dead Cap Allocation')).toBeVisible();
        await expect(page.locator('text=Cap Savings')).toBeVisible();

        // 3. Click the UI toggle to switch to Post-June 1
        await postJuneToggle.click();
        await expect(postJuneToggle).toHaveAttribute('aria-checked', 'true');

        // 4. Validate the Key Drivers SHAP accordion expands independently
        const shapAccordion = page.locator('summary', { hasText: 'KEY DRIVERS (SHAP)' });
        await expect(shapAccordion).toBeVisible();

        // Click and verify the inner contents become visible
        await shapAccordion.click();
        await expect(page.locator('text=Age Curve Decline')).toBeVisible();
    });
});
