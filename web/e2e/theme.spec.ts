import { expect, test, type Page } from "@playwright/test";

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
  await page.goto("/stats"); // not "/", which may resume the last open chapter
}

const theme = (page: Page) => page.evaluate(() => document.documentElement.dataset.theme);

async function choose(page: Page, name: "System" | "Light" | "Dark") {
  await page.getByRole("button", { name: /^Theme: / }).click();
  const saved = page.waitForResponse((r) => r.url().endsWith("/settings") && r.request().method() === "PUT");
  await page.getByRole("menuitemradio", { name }).click();
  await saved;
}

test("the theme choice follows the account across reloads and sign-ins", async ({ page, browser, baseURL }) => {
  await signIn(page);
  await choose(page, "Dark");
  expect(await theme(page)).toBe("dark");
  await page.reload({ waitUntil: "domcontentloaded" });
  expect(await theme(page)).toBe("dark"); // painted by index.html's inline script, before the bundle

  const other = await browser.newContext({ baseURL, colorScheme: "light" });
  const fresh = await other.newPage();
  await signIn(fresh);
  await expect.poll(() => theme(fresh)).toBe("dark"); // from the account, not this device
  await choose(fresh, "System");
  expect(await theme(fresh)).toBe("light");
  await other.close();
});

test("with System chosen the page follows the OS without a reload", async ({ page }) => {
  await signIn(page);
  await expect(page.getByRole("button", { name: "Theme: System" })).toBeVisible();
  await page.emulateMedia({ colorScheme: "dark" });
  await expect.poll(() => theme(page)).toBe("dark");
  await page.emulateMedia({ colorScheme: "light" });
  await expect.poll(() => theme(page)).toBe("light");
});
