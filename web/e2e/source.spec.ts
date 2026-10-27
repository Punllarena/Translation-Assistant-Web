import { expect, test } from "@playwright/test";
import { openChapter as openIn } from "./fixtures/library";

test("leaving Edit Source with unsaved text asks first", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
  await openIn(page, "E2E editor series", "E2E chapter");
  await page.getByRole("button", { name: "Chapter actions" }).click();
  await page.getByRole("menuitem", { name: "Edit source" }).click();
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
