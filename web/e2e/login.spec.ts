import { expect, test } from "@playwright/test";

test("a page opened right after sign-in is not replaced by the sign-in redirect", async ({ page }) => {
  // Hold the settings lookup that picks the post-sign-in page, so a click can happen while it is pending.
  await page.route("**/api/settings", async (route) => {
    if (route.request().method() === "GET") await new Promise((r) => setTimeout(r, 1000));
    await route.continue();
  });
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
  await page.getByRole("link", { name: "Statistics" }).click();
  await expect(page).toHaveURL(/\/stats$/);
  await page.waitForTimeout(1500); // past the held lookup
  await expect(page).toHaveURL(/\/stats$/);
});
