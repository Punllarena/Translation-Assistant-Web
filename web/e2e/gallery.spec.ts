import { expect, test, type Page } from "@playwright/test";
import { openSeries } from "./fixtures/library";

// Serial: the cover action and the delete change the seeded "Gallery spec" series for the
// tests that follow (and for nothing else).
test.describe.configure({ mode: "serial" });

const SERIES = "Gallery spec";
const tiles = (page: Page) => page.locator(".gallery-tile");
const viewer = (page: Page) => page.locator("dialog.gallery-viewer");

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
}

async function openGallery(page: Page) {
  await openSeries(page, SERIES);
  await page.getByRole("tab", { name: "Gallery" }).click();
}

test("shows the series' images with the cover first, and nothing opens the editor", async ({ page }) => {
  await signIn(page);
  await openGallery(page);
  await expect(tiles(page)).toHaveCount(4);
  await expect(tiles(page).nth(0).locator("img")).toHaveAttribute("src", /\/api\/covers\/\d+$/);
  await expect(tiles(page).nth(1).locator("img")).toHaveAttribute("src", /\/api\/images\/\d+$/);
  await expect(page.getByRole("heading", { name: "Vol 1" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Ch. 1 · Gallery chapter" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Illustrations" })).toBeVisible();
  // No way out to the editor from the Gallery.
  await expect(page.locator('a[href*="/documents/"]')).toHaveCount(0);
  await expect(page.getByRole("button", { name: /open in editor/i })).toHaveCount(0);
});

test("Set as volume cover replaces the cover tile", async ({ page }) => {
  await signIn(page);
  await openGallery(page);
  const cover = tiles(page).nth(0).locator("img");
  const before = await cover.getAttribute("src");
  await tiles(page).nth(1).click();
  await expect(viewer(page)).toBeVisible();
  await viewer(page).getByRole("button", { name: "Set as volume cover" }).click();
  await expect(viewer(page)).toBeHidden();
  await expect(tiles(page)).toHaveCount(4);
  await expect(tiles(page).nth(0).locator("img")).toHaveAttribute("src", /\/api\/covers\/\d+$/);
  await expect(tiles(page).nth(0).locator("img")).not.toHaveAttribute("src", before!);
});

test("deleting the Illustrations chapter's only image deletes the chapter", async ({ page }) => {
  await signIn(page);
  await openGallery(page);
  await tiles(page).nth(3).click();
  await expect(viewer(page)).toBeVisible();
  await viewer(page).getByRole("button", { name: "Delete" }).click();
  const confirm = page.getByRole("dialog", { name: "Delete image" });
  await expect(confirm.getByText(
    "This is the last image; the Illustrations chapter will be deleted too.")).toBeVisible();
  await confirm.getByRole("button", { name: "Delete" }).click();
  await expect(confirm).toBeHidden();
  await expect(tiles(page)).toHaveCount(3);
  await expect(page.getByRole("heading", { name: "Illustrations" })).toHaveCount(0);
  await page.getByRole("tab", { name: "Volumes" }).click();
  await expect(page.getByRole("link", { name: "Open Illustrations" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Open Gallery chapter" })).toBeVisible();
});
