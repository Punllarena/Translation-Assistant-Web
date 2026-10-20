import { expect, test, type Page } from "@playwright/test";
import { openSeries } from "./fixtures/library";

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
}

const numberOf = (page: Page, title: string) =>
  page.getByRole("row").filter({ hasText: title }).locator(".ch-num");

test("the shelf shows the series with its counts, and the List choice survives a reload", async ({ page }) => {
  await signIn(page);
  await page.goto("/");
  const tile = page.getByRole("link", { name: /E2E library series/ });
  await expect(tile).toContainText("1 vol · 3 ch");
  try {
    await page.getByRole("button", { name: "List" }).click();
    await expect(page.getByRole("button", { name: "List" })).toHaveAttribute("aria-pressed", "true");
    await page.reload();
    await expect(page.getByRole("button", { name: "List" })).toHaveAttribute("aria-pressed", "true");
  } finally {
    await page.getByRole("button", { name: "Bookshelf" }).click();
    await expect(page.getByRole("button", { name: "Bookshelf" })).toHaveAttribute("aria-pressed", "true");
  }
});

test("volumes number their chapters from 1, and loose chapters have their own entry", async ({ page }) => {
  await signIn(page);
  await openSeries(page, "E2E library series");
  await expect(page.getByRole("button", { name: /^Vol A/ })).toHaveAttribute("aria-current", "true");
  await expect(numberOf(page, "Lib one")).toHaveText("1");
  await expect(numberOf(page, "Lib two")).toHaveText("2");
  await page.getByRole("button", { name: /^No volume/ }).click();
  await expect(numberOf(page, "Lib loose")).toHaveText("1");
});

test("bulk delete and series delete ask first, and Cancel keeps everything", async ({ page }) => {
  await signIn(page);
  await openSeries(page, "E2E library series");
  await page.getByLabel("Select Lib one").check();
  await page.getByLabel("Select Lib two").check();
  await expect(page.getByText("2 selected")).toBeVisible();
  await page.getByRole("button", { name: "Delete", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("Delete 2 chapters? This can't be undone.")).toBeVisible();
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("link", { name: "Open Lib one" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Open Lib two" })).toBeVisible();

  await page.getByRole("tab", { name: "Settings" }).click();
  await page.getByRole("button", { name: "Delete series" }).click();
  await expect(dialog.getByText('Delete "E2E library series" and its 3 chapters? This can\'t be undone.')).toBeVisible();
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toBeHidden();
});
