import { test, expect } from '@playwright/test';

// Sprint 9: Persona Architecture Verification
// Note: As of Sprint 10, GM, Agent, and Bettor routes are protected by Clerk.

test.describe('Sprint 9: Persona Routing Architecture', () => {

    test('Root Landing Page renders the Persona Showcase', async ({ page }) => {
        await page.goto('/');
        await expect(page.getByText('Choose your Persona.')).toBeVisible();
        await expect(page.getByText('The Front Office').first()).toBeVisible();
        await expect(page.getByText('The Agent').first()).toBeVisible();
        await expect(page.getByText('The Sharp').first()).toBeVisible();
        await expect(page.getByText('The Armchair GM').first()).toBeVisible();
    });

    test('Front Office (GM) Dashboard redirects to Auth', async ({ page }) => {
        await page.goto('/dashboard/gm');
        await expect(page).toHaveURL(/.*sign-in.*/);
    });

    test('Agent Dashboard redirects to Auth', async ({ page }) => {
        await page.goto('/dashboard/agent');
        await expect(page).toHaveURL(/.*sign-in.*/);
    });

    test('Fan Dashboard resolves and mounts components (Public)', async ({ page }) => {
        await page.goto('/dashboard/fan');
        await expect(page.getByRole('heading', { name: /Armchair GM/i })).toBeVisible({ timeout: 10000 });
        await expect(page.getByText('Franchise Power Rankings')).toBeVisible();
    });

    test('Sharp (Bettor) Dashboard redirects to Auth', async ({ page }) => {
        await page.goto('/dashboard/bettor');
        await expect(page).toHaveURL(/.*sign-in.*/);
    });

});
