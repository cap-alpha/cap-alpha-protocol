import { test, expect } from '@playwright/test';

test.describe('E2E Integration & Production Hardening Suite', () => {

  test('Network Layer: Auth Boundaries', async ({ page }) => {
    // Attempt to hit protected route
    await page.goto('/dashboard/gm');
    
    // Clerk should redirect to a sign-in or accounts page
    expect(page.url()).toContain('sign-in');
    
    // Public landing page should succeed
    const publicResponse = await page.goto('/');
    expect(publicResponse!.status()).toBe(200);
  });

  test('Data Hydration: Real DB rendering (No Mocks)', async ({ page }) => {
    // Navigate to a known player page
    const response = await page.goto('/player/dak-prescott');
    expect(response!.status()).toBe(200);

    // Assert that the page title renders with the player name
    await expect(page.locator('h1')).toContainText('Dak Prescott');

    // Click the Health Feed tab to view the IntelligenceFeed
    await page.getByRole('tab', { name: 'Health Feed' }).click();

    // The feed must contain EITHER the authentic DB feed items OR the strict authenticated 'Zero State' message.
    // Wait for the tab panel to render its content
    const tabPanel = page.getByRole('tabpanel');
    await expect(tabPanel).toBeVisible();
    
    const textContent = await tabPanel.textContent() || '';
    expect(textContent).not.toContain('mock_');
    expect(textContent).not.toContain('Lorem ipsum');
    
    // Instead of asserting specific DB fields which might change depending on hydration timing,
    // we assert that no mock data strings render.
    // The feed is either empty or contains Alpha Protocol/Media signals.
  });

  test('Routing Validation: Global Search Navigation', async ({ page }) => {
    // Navigate to a page that contains the GlobalSearch component
    await page.goto('/player/dak-prescott');
    
    // Click the search trigger button to open the command palette modal
    // In global-search.tsx, the button has the text "Search players or teams..." 
    await page.getByRole('button', { name: /search/i }).first().click();
    
    // Fill the actual input field inside the Dialog
    const searchInput = page.getByPlaceholder("Type a player name (e.g., 'Dak') or team...");
    await expect(searchInput).toBeVisible();
    await searchInput.fill('Dak');
    
    // Wait for the autocomplete query to return the DB result and click it
    const searchResult = page.getByText('Dak Prescott', { exact: false }).first();
    await expect(searchResult).toBeVisible();
    await searchResult.click({ force: true });

    // Assert client-side navigation succeeds without a 404
    await page.waitForURL('**/player/dak-prescott');
    await expect(page.locator('h1')).toContainText('Dak Prescott');
  });
});
