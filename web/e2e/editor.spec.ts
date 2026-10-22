import { expect, test, type Page } from "@playwright/test";
import { openChapter as openIn, openSeries } from "./fixtures/library";

async function openChapter(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
  await openIn(page, "E2E editor series", "E2E chapter");
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
  await expect(page.getByText("Saved", { exact: true })).toBeVisible({ timeout: 5_000 });
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
  await expect(page.getByText("Saved", { exact: true })).toBeVisible({ timeout: 5_000 });
  await page.reload();
  await expect(page.getByText("Typed while expired.")).toBeVisible();
});

test("no profile picker; Add to dictionary for this series or for all series", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
  await openIn(page, "E2E editor series", "Spell target");
  await expect(page.getByText("zorbleq quuxbarr", { exact: true }).first()).toBeVisible();
  await expect(page.getByLabel("Profile")).toHaveCount(0);
  const box = page.getByRole("textbox", { name: "Translation" });
  const flagged = box.locator(".misspelled");
  await expect(flagged).toHaveCount(2, { timeout: 5_000 });

  await flagged.filter({ hasText: "zorbleq" }).click({ button: "right" });
  await page.getByRole("menuitem", { name: "Add “zorbleq” to this series" }).click();
  await expect(page.getByText("Added “zorbleq” to the series dictionary")).toBeVisible();
  await expect(flagged).toHaveCount(1);

  await flagged.filter({ hasText: "quuxbarr" }).click({ button: "right" });
  await page.getByRole("menuitem", { name: "Add “quuxbarr” for all series" }).click();
  await expect(page.getByText("Added “quuxbarr” to your dictionary")).toBeVisible();
  await expect(flagged).toHaveCount(0);

  // Each word landed in its own list.
  await page.goto("/settings/editor");
  const account = page.getByRole("region", { name: "Dictionary" });
  await expect(account.getByRole("button", { name: "Remove “quuxbarr”" })).toBeVisible();
  await expect(account.getByRole("button", { name: "Remove “zorbleq”" })).toHaveCount(0);
  await openSeries(page, "E2E editor series");
  await page.getByRole("tab", { name: "Glossary" }).click();
  const series = page.getByRole("region", { name: "Series dictionary" });
  await expect(series.getByRole("button", { name: "Remove “zorbleq”" })).toBeVisible();
  await expect(series.getByRole("button", { name: "Remove “quuxbarr”" })).toHaveCount(0);
});
