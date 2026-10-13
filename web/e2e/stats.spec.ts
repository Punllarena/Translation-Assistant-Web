import { expect, test } from "@playwright/test";

test("statistics show today's work and the series breakdown", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
  await page.getByRole("link", { name: "Statistics" }).click();
  await expect(page.getByRole("img", { name: /Activity heatmap/ })).toBeVisible();
  await expect(page.getByText(/Current streak: [1-9]\d* days/)).toBeVisible();
  await expect(page.getByRole("cell", { name: "E2E stats series" })).toBeVisible();
});
