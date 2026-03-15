import { test, expect } from '@playwright/test';

// Sprint 9: Persona Architecture Verification
// These tests verify that the monolithic dashboard was correctly dismantled
// and that all 4 unique persona namespaces resolve and mount their respective MVPs.

test.describe('Sprint 9: Persona Routing Architecture', () => {

    test('Root Landing Page renders the Persona Showcase', async ({ page }) => {
        await page.goto('/');
        
        // Ensure the landing page no longer redirects to /dashboard instantly 
        // and instead asks the user to choose their persona.
        await expect(page.getByText('Choose your Persona.')).toBeVisible();
        
        // Verify all 4 personas are available as toggles
        await expect(page.getByText('The Front Office')).toBeVisible();
        await expect(page.getByText('The Agent')).toBeVisible();
        await expect(page.getByText('The Sharp')).toBeVisible();
        await expect(page.getByText('The Armchair GM')).toBeVisible();
    });

    test('Front Office (GM) Dashboard resolves and mounts components', async ({ page }) => {
        await page.goto('/dashboard/gm');
        
        // Wait for hydration/data fetch
        await expect(page.getByRole('heading', { name: /Front Office/i })).toBeVisible({ timeout: 10000 });
        await expect(page.getByText('Adversarial Trade Engine')).toBeVisible();
    });

    test('Agent Dashboard resolves and mounts components', async ({ page }) => {
        await page.goto('/dashboard/agent');
        
        await expect(page.getByRole('heading', { name: /Agent/i })).toBeVisible({ timeout: 10000 });
        await expect(page.getByText('Surplus Value Leaderboard')).toBeVisible();
    });

    test('Fan Dashboard resolves and mounts components', async ({ page }) => {
        await page.goto('/dashboard/fan');
        
        await expect(page.getByRole('heading', { name: /Armchair GM/i })).toBeVisible({ timeout: 10000 });
        await expect(page.getByText('Franchise Power Rankings')).toBeVisible();
    });

    test('Sharp (Bettor) Dashboard resolves and mounts components', async ({ page }) => {
        await page.goto('/dashboard/bettor');
        
        await expect(page.getByRole('heading', { name: /Alpha Terminal/i })).toBeVisible({ timeout: 10000 });
        await expect(page.getByText('Consensus Lead Time')).toBeVisible();
    });

});
