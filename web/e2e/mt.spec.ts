import { expect, test } from "@playwright/test";
import { openChapter as openIn } from "./fixtures/library";

test("the Dictionary card merges JParser and MeCab for the active line", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
  await openIn(page, "E2E mt series", "MT target");
  const dictionary = page.getByRole("region", { name: "Dictionary" });
  await expect(dictionary).toContainText("猫");
  await expect(dictionary).toContainText("cat");
  await expect(dictionary).toContainText("ネコ");
});
