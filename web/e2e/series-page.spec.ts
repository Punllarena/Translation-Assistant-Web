import { expect, test, type Page } from "@playwright/test";
import { openSeries } from "./fixtures/library";

// These tests run in order: the last one deletes a seeded chapter, so the earlier ones go first.

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
}

const SERIES = "Series page spec";
const row = (page: Page, text: string) => page.getByRole("row").filter({ hasText: text });
const overflow = (page: Page) =>
  page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);

test.describe.configure({ mode: "serial" });

test("a row click in select mode ticks it and never opens the editor", async ({ page }) => {
  await signIn(page);
  await openSeries(page, SERIES);
  await page.getByLabel("Select Spec one").check();
  await expect(page.getByText("1 selected")).toBeVisible();
  const before = page.url();
  await row(page, "Spec image").locator(".ch-title").click();
  await expect(page.getByText("2 selected")).toBeVisible();
  expect(page.url()).toBe(before);
  await expect(page.getByRole("button", { name: "Clear" })).toBeVisible();
  await page.getByRole("button", { name: "Clear" }).click();
  await expect(page.getByText("2 selected")).toHaveCount(0);
});

test("shift-click ticks the range of shown rows", async ({ page }) => {
  await signIn(page);
  await openSeries(page, SERIES);
  await page.getByLabel("Select Spec one").check();
  await row(page, "Spec image").locator(".ch-title").click({ modifiers: ["Shift"] });
  await expect(page.getByText("3 selected")).toBeVisible();
});

test("a 200-character title does not push the page sideways", async ({ page }) => {
  await signIn(page);
  await openSeries(page, SERIES);
  for (const [width, height] of [[1280, 800], [375, 812]] as const) {
    await page.setViewportSize({ width, height });
    expect(await overflow(page), `${width}×${height}`).toBeLessThanOrEqual(0);
  }
});

test("Columns shows a column, and the choice survives a reload", async ({ page }) => {
  await signIn(page);
  await openSeries(page, SERIES);
  const imagesHeader = page.getByRole("columnheader", { name: "Images" });
  await expect(imagesHeader).toHaveCount(0);
  await page.getByRole("button", { name: "Columns ▾" }).click();
  await page.getByRole("menuitemcheckbox", { name: "Images" }).click();
  await expect(imagesHeader).toBeVisible();
  await page.keyboard.press("Escape");
  await page.reload();
  await expect(page.getByRole("columnheader", { name: "Images" })).toBeVisible();
  // back to the defaults, so the rest of the suite sees the usual columns
  await page.getByRole("button", { name: "Columns ▾" }).click();
  await page.getByRole("menuitemcheckbox", { name: "Images" }).click();
  await expect(page.getByRole("columnheader", { name: "Images" })).toHaveCount(0);
});

test("Select mode with nothing ticked shows quick picks but no selection bar", async ({ page }) => {
  await signIn(page);
  await openSeries(page, SERIES);
  const chapters = await page.locator(".chapters tbody tr").count();
  const tools = page.locator(".ch-tools");
  await tools.getByRole("button", { name: "Select", exact: true }).click();
  await expect(page.getByRole("toolbar", { name: "Selected chapters" })).toHaveCount(0);
  await tools.getByRole("button", { name: "Select ▾" }).click();
  await page.getByRole("menuitem", { name: "All", exact: true }).click();
  await expect(page.getByRole("toolbar", { name: "Selected chapters" })).toBeVisible();
  await expect(page.getByText(`${chapters} selected`)).toBeVisible();
});

test("the Volumes tab has no series-wide Ollama buttons, and the Tools tab has them", async ({ page }) => {
  await signIn(page);
  await openSeries(page, SERIES);
  await expect(page.getByRole("button", { name: "Queue series for Ollama" })).toHaveCount(0);
  await page.getByRole("tab", { name: "Tools" }).click();
  await expect(page.getByRole("button", { name: "Queue series for Ollama" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Flush Ollama output…" })).toBeVisible();
});

test("the selection bar offers Organise with Move to and Merge, and Merge needs two rows", async ({ page }) => {
  await signIn(page);
  await openSeries(page, SERIES);
  await page.getByLabel("Select Spec one").check();
  await expect(page.getByRole("button", { name: "Move to…" })).toHaveCount(0);
  const organise = page.getByRole("button", { name: "Organise ▾" });
  await organise.click();
  await expect(page.getByRole("menuitem", { name: "Merge" })).toBeDisabled();
  await page.getByLabel("Select Spec image").check();
  await organise.click();
  await expect(page.getByRole("menuitem", { name: "Merge" })).toBeEnabled();
  await page.keyboard.press("Escape");
  await expect(organise).toBeFocused();
});

test("deleting a chapter with an image offers to move it, and the Illustrations chapter appears", async ({ page }) => {
  await signIn(page);
  await openSeries(page, SERIES);
  await page.getByLabel("Select Spec image").check();
  await page.getByRole("button", { name: "Delete", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("Move their images to the volume's Illustrations chapter")).toBeVisible();
  await dialog.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("link", { name: "Open Illustrations" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Open Spec image" })).toHaveCount(0);
});
