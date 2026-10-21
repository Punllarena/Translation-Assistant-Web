import { expect, test } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { openSeries } from "./fixtures/library";

const here = path.dirname(fileURLToPath(import.meta.url));

async function openImport(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
  await page.goto("/");
  await page.getByRole("link", { name: "Import…" }).click();
  await expect(page.getByRole("heading", { name: "Import", exact: true })).toBeVisible();
}

const txt = (name: string, raw: string) => ({
  name, mimeType: "text/plain",
  buffer: Buffer.from(`${raw}\n---SEPERATOR---\n\n`),
});

test("batch import of TXT files into a new series", async ({ page }) => {
  await openImport(page);
  await page.getByLabel("Files to import").setInputFiles([
    txt("Batch A.txt", "鳥がいる。"), txt("Batch B.txt", "犬がいる。"),
  ]);
  await page.getByLabel("New series title").first().fill("Import Batch");
  await page.getByRole("button", { name: "Import", exact: true }).click();
  await expect(page.getByRole("status").getByText("Imported: 2")).toBeVisible();
  await page.goto("/");
  await page.getByRole("link", { name: "Import Batch", exact: true }).click();
  await expect(page.getByRole("link", { name: "Open Batch A" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Open Batch B" })).toBeVisible();
});

test("EPUB import: inspect, pick chapters, import", async ({ page }) => {
  await openImport(page);
  await page.getByLabel("EPUB file").setInputFiles(path.join(here, "fixtures/sample.epub"));
  await expect(page.getByText(/1\. Neko chapter/)).toBeVisible();
  await expect(page.getByText(/2\. Inu chapter/)).toBeVisible();
  await expect(page.getByLabel("Author")).toHaveValue("E2E Author");
  for (const box of await page.getByRole("checkbox").all()) await box.check();
  // The new series is named after the book, so the name starts as Volume 1, not "Book - Book".
  await expect(page.getByLabel("Number", { exact: true })).toHaveValue("1");
  await expect(page.getByLabel("Subtitle", { exact: true })).toHaveValue("");
  const title = page.getByLabel("New series title").last();
  await title.fill("Import EPUB");
  await expect(page.getByLabel("Number", { exact: true })).toHaveValue(""); // untouched fields follow the series
  await page.getByLabel("Subtitle", { exact: true }).fill("First");
  await title.fill("Import EPUB 2");
  await title.fill("Import EPUB");
  await expect(page.getByLabel("Subtitle", { exact: true })).toHaveValue("First"); // edited fields stay
  await page.getByRole("button", { name: "Import", exact: true }).last().click();
  await expect(page.getByRole("status").getByText("Imported: 2")).toBeVisible();
  await page.getByRole("link", { name: "Open series" }).click();
  await expect(page.getByText("Neko chapter").first()).toBeVisible();
});

test("New volume can import an EPUB into the open series", async ({ page }) => {
  await openImport(page);
  await openSeries(page, "E2E epub volume series");
  await page.getByRole("button", { name: "New volume" }).click();
  const dialog = page.getByRole("dialog", { name: "New volume" });
  await dialog.getByRole("button", { name: "Import EPUB" }).click();
  await dialog.getByLabel("EPUB file").setInputFiles(path.join(here, "fixtures/sample.epub"));
  await expect(dialog.getByText(/1\. Neko chapter/)).toBeVisible();
  for (const box of await dialog.getByRole("checkbox").all()) await box.check();
  await dialog.getByLabel("Subtitle").fill("Vol from EPUB");
  await dialog.getByRole("button", { name: "Import", exact: true }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("button", { name: /^Vol from EPUB/ })).toHaveAttribute("aria-current", "true");
  await expect(page.getByRole("link", { name: "Open Neko chapter" })).toBeVisible();
});
