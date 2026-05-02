import { test, expect } from "@playwright/test";

test.describe("Prediction Outcome Stamp — L4 Design Language", () => {
  test("homepage renders at least one outcome stamp", async ({ page }) => {
    await page.goto("/");

    // At least one stamp element must exist in the DOM
    const stamps = page.locator('[data-testid="outcome-stamp"]');
    await expect(stamps.first()).toBeVisible({ timeout: 10_000 });
  });

  test("outcome stamp carries the correct data-outcome attribute", async ({
    page,
  }) => {
    await page.goto("/");

    const stamps = page.locator('[data-testid="outcome-stamp"]');
    await expect(stamps.first()).toBeVisible({ timeout: 10_000 });

    // The data-outcome attribute must be one of the four valid values
    const outcomeAttr = await stamps.first().getAttribute("data-outcome");
    expect(["correct", "incorrect", "pending", "void"]).toContain(outcomeAttr);
  });

  test("outcome stamp displays recognisable text for its outcome", async ({
    page,
  }) => {
    await page.goto("/");

    const stamps = page.locator('[data-testid="outcome-stamp"]');
    await expect(stamps.first()).toBeVisible({ timeout: 10_000 });

    const outcomeAttr = await stamps.first().getAttribute("data-outcome");
    const textContent = (await stamps.first().textContent()) ?? "";

    const expected: Record<string, string> = {
      correct: "CORRECT",
      incorrect: "INCORRECT",
      pending: "PENDING",
      void: "VOID",
    };

    if (outcomeAttr && expected[outcomeAttr]) {
      expect(textContent.toUpperCase()).toContain(expected[outcomeAttr]);
    }
  });
});
