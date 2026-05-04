/**
 * WCAG AA accessibility tests (axe-core)
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
 */

import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const ROUTES = ['/', '/ledger', '/status', '/legal/terms', '/legal/corrections'];

for (const route of ROUTES) {
  test(`WCAG AA: ${route}`, async ({ page }) => {
    await page.goto(route);
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa'])
      .analyze();
    expect(results.violations).toEqual([]);
  });
}
