import { expect, type Page } from "@playwright/test";

/** From the Library to a series' Volumes tab (the page must already be signed in). */
export async function openSeries(page: Page, title: string) {
  await page.goto("/");
  await page.getByRole("link", { name: title, exact: true }).click();
  await expect(page.getByRole("tab", { name: "Volumes" })).toBeVisible();
}

/** From the Library to a chapter's editor, choosing its volume first when it is not the selected one. */
export async function openChapter(page: Page, seriesTitle: string, chapterTitle: string, volume?: string) {
  await openSeries(page, seriesTitle);
  if (volume) await page.getByRole("button", { name: new RegExp(`^${volume}`) }).click();
  await page.getByRole("link", { name: `Open ${chapterTitle}` }).click();
}
