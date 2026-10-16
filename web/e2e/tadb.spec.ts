import path from "node:path";
import { expect, test } from "@playwright/test";

test("a user imports a desktop ta.db after reading the dry run", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("tadb@example.com");
  await page.getByLabel("Password").fill("tadb-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));
  await page.goto("/import");
  await page.getByLabel("Desktop ta.db").setInputFiles(path.resolve(import.meta.dirname, ".generated/ta.db"));
  const card = page.getByRole("region", { name: "Desktop library (ta.db)" });
  await expect(card.getByRole("columnheader", { name: "Would add" })).toBeVisible();
  await card.getByRole("button", { name: "Import", exact: true }).click();
  await expect(card.getByText("Imported.")).toBeVisible();
  await page.goto("/");
  await expect(page.getByRole("link", { name: "My Series" })).toBeVisible();
});
