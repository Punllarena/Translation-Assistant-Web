import { expect, test, type Page } from "@playwright/test";
import { openChapter, openSeries } from "./fixtures/library";

// The seeded chapter's title is 原題の章 and its chapter_title "Shown chapter title", as a
// translated chapter imported from the desktop's ta.db is.

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
}

const SERIES = "E2E display title series";

test.describe.configure({ mode: "serial" });

test("the chapter list and editor show the chapter title", async ({ page }) => {
  await signIn(page);
  await openChapter(page, SERIES, "Shown chapter title");
  await expect(page.getByRole("button", { name: /Shown chapter title/ })).toContainText("Shown chapter title");
  await page.goto(page.url() + "/source");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Edit source — Shown chapter title");
});

test("Rename edits the shown title", async ({ page }) => {
  await signIn(page);
  await openSeries(page, SERIES);
  await page.getByRole("button", { name: "Actions for Shown chapter title" }).click();
  await page.getByRole("menuitem", { name: "Rename…" }).click();
  const dialog = page.getByRole("dialog", { name: "Rename chapter" });
  await expect(dialog.getByText("Original title: 原題の章")).toBeVisible();
  await expect(dialog.getByLabel("Title")).toHaveValue("Shown chapter title");
  await dialog.getByLabel("Title").fill("Renamed chapter title");
  await dialog.getByRole("button", { name: "Rename" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("link", { name: "Open Renamed chapter title" })).toBeVisible();
});
