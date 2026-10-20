import { expect, test } from "@playwright/test";
import { openChapter as openIn } from "./fixtures/library";

test("JParser and MeCab cards analyse the active line", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
  await openIn(page, "E2E mt series", "MT target");
  const jparser = page.getByRole("region", { name: "JParser" });
  await expect(jparser).toContainText("猫");
  await expect(jparser).toContainText("cat");
  await expect(page.getByRole("region", { name: "MeCab" })).toContainText("ネコ");
});
