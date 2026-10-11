import { expect, test } from "@playwright/test";

test("glossary: add, reorder, save, import with BOM and duplicate", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
  await page.goto("/settings/profiles");
  await expect(page.getByRole("heading", { name: "Glossary" })).toBeVisible();
  await page.getByRole("button", { name: "Add row" }).click();
  await page.getByLabel("Phrase 1").fill("alpha");
  await page.getByLabel("Translation 1").fill("big wolf");
  await page.getByRole("button", { name: "Add row" }).click();
  await page.getByLabel("Phrase 2").fill("beta");
  await page.getByRole("button", { name: "Move 2 up" }).click();
  await expect(page.getByLabel("Phrase 1")).toHaveValue("beta");
  await page.getByRole("button", { name: "Save glossary" }).click();
  await expect(page.getByRole("status")).toHaveText("Saved");
  await page.reload();
  await expect(page.getByLabel("Phrase 1")).toHaveValue("beta");
  await expect(page.getByLabel("Translation 2")).toHaveValue("big_wolf");

  await page.getByLabel("Import CSV").setInputFiles({
    name: "g.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("﻿gamma,three words\nalpha,wolf\nalpha,dup\n"),
  });
  await expect(page.getByRole("status")).toContainText("Imported:");
  await expect(page.getByLabel("Phrase 3")).toHaveValue("gamma");

  // Unsaved edits survive a declined navigation.
  await page.getByRole("button", { name: "Add row" }).click();
  await page.getByLabel("Phrase 4").fill("unsaved");
  const dialogs: string[] = [];
  page.once("dialog", (d) => { dialogs.push(d.message()); void d.dismiss(); });
  await page.getByRole("link", { name: "Shortcuts" }).click();
  await expect.poll(() => dialogs.length).toBe(1);
  expect(dialogs[0]).toContain("Discard unsaved glossary edits?");
  await expect(page).toHaveURL(/\/settings\/profiles/);
  await expect(page.getByLabel("Phrase 4")).toHaveValue("unsaved");
});
