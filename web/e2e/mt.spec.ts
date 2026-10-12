import { expect, test } from "@playwright/test";

test("JParser and MeCab cards analyse the active line", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
  await page.goto("/");
  await page.getByRole("link", { name: "Open MT target" }).click();
  const jparser = page.getByRole("region", { name: "JParser" });
  await expect(jparser).toContainText("猫");
  await expect(jparser).toContainText("cat");
  await expect(page.getByRole("region", { name: "MeCab" })).toContainText("ネコ");
});
