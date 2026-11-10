import { expect, test, type Page } from "@playwright/test";
import { openChapter as openIn } from "./fixtures/library";

async function openEditSource(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
  await openIn(page, "E2E editor series", "E2E chapter");
  await page.getByRole("button", { name: "Chapter actions" }).click();
  await page.getByRole("menuitem", { name: "Edit source" }).click();
}

test("emptying Edit Source asks before saving; Cancel restores the text, Remove saves it empty", async ({ page }) => {
  await openEditSource(page);
  const editor = page.locator(".source-editor .cm-content");
  const before = await editor.textContent();
  await editor.click();
  await page.keyboard.press("ControlOrMeta+a");
  await page.keyboard.press("Delete");
  const dialog = page.getByRole("dialog", { name: "Remove all text?" });
  await page.getByRole("button", { name: "Save" }).click();
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toBeHidden();
  await expect(page).toHaveURL(/\/source$/);
  await expect(editor).toHaveText(before);
  await editor.click();
  await page.keyboard.press("ControlOrMeta+a");
  await page.keyboard.press("Delete");
  await page.getByRole("button", { name: "Save" }).click();
  await dialog.getByRole("button", { name: "Remove" }).click();
  await expect(page).not.toHaveURL(/\/source$/);
});

test("leaving Edit Source with unsaved text asks first", async ({ page }) => {
  await openEditSource(page);
  await page.locator(".source-editor .cm-content").click();
  await page.keyboard.type("x");
  // The confirm runs in an effect after the click returns, so wait for each dialog explicitly.
  const library = page.getByRole("banner").getByRole("link", { name: "Library" });
  const dismissed = page.waitForEvent("dialog").then((d) => d.dismiss());
  await library.click();
  await dismissed;
  await expect(page).toHaveURL(/\/source$/);
  const accepted = page.waitForEvent("dialog").then((d) => d.accept());
  await library.click();
  await accepted;
  await expect(page).toHaveURL(/\/$/);
});
