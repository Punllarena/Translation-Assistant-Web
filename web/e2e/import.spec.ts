import { expect, test } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

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
    txt("Batch A.txt", "猫がいる。"), txt("Batch B.txt", "犬がいる。"),
  ]);
  await page.getByLabel("New series title").first().fill("Import Batch");
  await page.getByRole("button", { name: "Import", exact: true }).click();
  await expect(page.getByRole("status").getByText("Imported: 2")).toBeVisible();
  await page.goto("/");
  await expect(page.getByRole("link", { name: "Import Batch", exact: true })).toBeVisible();
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
  const title = page.getByLabel("New series title").last();
  await title.fill("Import EPUB");
  await page.getByRole("button", { name: "Import", exact: true }).last().click();
  await expect(page.getByRole("status").getByText("Imported: 2")).toBeVisible();
  await page.getByRole("link", { name: "Open series" }).click();
  await expect(page.getByText("Neko chapter").first()).toBeVisible();
});
