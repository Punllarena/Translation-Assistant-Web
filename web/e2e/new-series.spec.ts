import { expect, test, type Page } from "@playwright/test";

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
}

test("New series offers three sources", async ({ page }) => {
  await signIn(page);
  await page.goto("/");
  await page.getByRole("link", { name: "New series" }).first().click();
  await expect(page).toHaveURL(/\/new$/);
  await expect(page.getByRole("button", { name: /Syosetu/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /EPUB/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Paste/ })).toBeVisible();
});

test("Paste creates an empty series with credits", async ({ page }) => {
  await signIn(page);
  await page.goto("/new");
  await page.getByRole("button", { name: /Paste/ }).click();
  await page.getByLabel("Title", { exact: true }).fill("NS Paste");
  await page.getByLabel("Japanese title").fill("貼り付け");
  await page.getByLabel("Author (romaji)").fill("Harituke");
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page).toHaveURL(/\/series\/\d+/);
  await page.getByRole("tab", { name: "Settings" }).click();
  await expect(page.getByLabel("Japanese title")).toHaveValue("貼り付け");
});

test("A taken title is refused", async ({ page }) => {
  await signIn(page);
  await page.goto("/new?source=paste");
  await page.getByLabel("Title", { exact: true }).fill("NS Paste");
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("alert")).toContainText("a series with that title exists");
});
