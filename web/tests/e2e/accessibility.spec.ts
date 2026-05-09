/**
 * WCAG AA accessibility tests (axe-core) — issue #505
 *
 * Verifies that key routes pass WCAG 2.0 Level A and AA rules via axe-core.
 *
 * Prerequisites:
 *   - A running app at PLAYWRIGHT_BASE_URL (default: http://localhost:3000)
 *   - Run locally with: make up && make test-e2e
 *   - In CI these tests run inside Docker alongside the app container.
 *
 * All violations are reported as test failures with a structured diff showing
 * each failing rule, the impacted element(s), and a help URL.
 *
 * Routes tested: /, /ledger, /legal/terms (routes that exist in the current app).
 * Removed /status and /legal/corrections — those routes do not exist in the current codebase.
 */

import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const ROUTES = ['/', '/ledger', '/legal/terms'];

for (const route of ROUTES) {
  test(`WCAG AA: ${route}`, async ({ page }) => {
    await page.goto(route);
    // Wait for the page to fully render before running axe
    await page.waitForLoadState('domcontentloaded');
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa'])
      // Exclude third-party Clerk auth widget — it renders in an iframe
      // and is not under our control for accessibility remediation.
      .exclude('#clerk-components')
      .analyze();
    expect(results.violations).toEqual([]);
  });
}
