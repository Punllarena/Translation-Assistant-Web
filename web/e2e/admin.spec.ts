import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));
}

test("an admin changes a server setting and resets it", async ({ page }) => {
  await signIn(page);
  await page.getByRole("link", { name: "Admin" }).click();
  const delay = page.getByLabel("Seconds between syosetu requests", { exact: true });
  const before = await delay.inputValue();
  await delay.fill("7");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Saved" })).toBeVisible();
  await expect(delay).toHaveValue("7");
  await page.getByRole("button", { name: "Reset Seconds between syosetu requests" }).click();
  await expect(delay).toHaveValue(before);
});

test("an admin creates an invite link and revokes it", async ({ page }) => {
  await signIn(page);
  await page.goto("/admin");
  await page.getByLabel("Email (optional)").fill("friend@example.com");
  await page.getByRole("button", { name: "Create invite" }).click();
  await expect(page.getByLabel("Invite link")).toHaveValue(/\/invite\?token=/);
  const row = page.getByRole("row", { name: /friend@example\.com/ });
  await expect(row).toContainText("pending");
  await row.getByRole("button", { name: "Revoke" }).click();
  await expect(row).toHaveCount(0);
});

test("an admin uploads a Conjugations file; the env-set EDICT2 is read-only", async ({ page }) => {
  await signIn(page);
  await page.goto("/admin");
  await expect(page.getByRole("group", { name: "EDICT2" })).toContainText("set by the server's environment");
  await expect(page.getByRole("group", { name: "EDICT2" }).getByRole("button", { name: "Download from EDRDG" })).toHaveCount(0);
  await page.getByLabel("Upload Conjugations").setInputFiles(
    path.resolve(import.meta.dirname, "../../tests/fixtures/mt/conjugations_sample.json"));
  await expect(page.getByRole("group", { name: "Conjugations" })).toContainText(/\d+ rules/);
  await page.getByRole("group", { name: "Conjugations" }).getByRole("button", { name: "Remove" }).click();
  await expect(page.getByRole("group", { name: "Conjugations" })).toContainText("Not installed");
});
