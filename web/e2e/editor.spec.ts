import { expect, test, type Page } from "@playwright/test";

async function openChapter(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
  await page.goto("/");
  await page.getByRole("link", { name: "Open E2E chapter" }).click();
}

test("sign in and open a document", async ({ page }) => {
  await openChapter(page);
  await expect(page.getByText("一行目です。")).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Translation" })).toBeFocused();
});

test("translate two lines and the save indicator settles", async ({ page }) => {
  await openChapter(page);
  await page.getByRole("textbox", { name: "Translation" }).click();
  await page.keyboard.type("This is the first line.");
  await page.keyboard.press("Enter");
  await page.keyboard.type("This is the second line.");
  await expect(page.getByRole("status")).toHaveText("Saved", { timeout: 5_000 });
  await page.reload();
  await expect(page.getByText("This is the first line.")).toBeVisible();
  await expect(page.getByText("This is the second line.")).toBeVisible();
});
