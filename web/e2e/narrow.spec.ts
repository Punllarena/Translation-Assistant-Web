import { expect, test, type Page } from "@playwright/test";

test.use({ viewport: { width: 390, height: 844 } });

const overflow = (page: Page) =>
  page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

test("sign-in fits a phone", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  expect(await overflow(page)).toBeLessThanOrEqual(0);
});

test("restyled pages fit a phone without sideways scrolling", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
  for (const path of ["/stats", "/settings/editor", "/settings/mt", "/settings/wp", "/settings/shortcuts", "/import"]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    expect(await overflow(page), path).toBeLessThanOrEqual(0);
  }
});

test("the heatmap shows today on a phone and scrolls inside its box", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
  await page.goto("/stats");
  const today = page.locator("svg.heatmap rect").last();
  await expect(today).toBeVisible();
  const box = await today.boundingBox();
  expect(box!.x + box!.width).toBeLessThanOrEqual(390); // today's cell is on screen, not clipped away
  expect(await overflow(page)).toBeLessThanOrEqual(0);
});
