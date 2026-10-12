import { expect, test } from "@playwright/test";

test("machine translation: DeepL key persists and enables the panel", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
  await page.getByRole("link", { name: "Machine translation" }).click();
  await expect(page.getByRole("heading", { name: "Machine translation" })).toBeVisible();
  const show = page.getByLabel("Show DeepL");
  await show.check();
  await expect(page.getByRole("status")).toHaveText("Saved");
  await page.getByLabel("DeepL API key").fill("test-key:fx");
  await page.getByRole("button", { name: "Save DeepL" }).click();
  await expect(page.getByText("…y:fx")).toBeVisible();
  await page.reload();
  await expect(page.getByText("…y:fx")).toBeVisible();
  await expect(page.getByTestId("status-deepl")).toHaveText("Ready");
  await expect(show).toBeChecked();
  await show.uncheck();
  await expect(page.getByRole("status")).toHaveText("Saved");
  await page.reload();
  await expect(show).not.toBeChecked();
});
