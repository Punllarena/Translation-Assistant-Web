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

test("a session that expires mid-edit signs out, then restores and saves the text", async ({ page }) => {
  await openChapter(page);
  const expired = "**/api/documents/*/lines";
  await page.route(expired, (route) =>
    route.request().method() === "PATCH"
      ? route.fulfill({ status: 401, contentType: "application/json", body: '{"detail":"session invalid or expired"}' })
      : route.fallback(),
  );
  await page.getByRole("textbox", { name: "Translation" }).click();
  await page.keyboard.type("Typed while expired.");
  await page.waitForURL(/\/login/, { timeout: 10_000 });
  await page.unroute(expired);
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL(/\/documents\//);
  await expect(page.getByText("Typed while expired.")).toBeVisible();
  await expect(page.getByRole("status")).toHaveText("Saved", { timeout: 5_000 });
  await page.reload();
  await expect(page.getByText("Typed while expired.")).toBeVisible();
});
