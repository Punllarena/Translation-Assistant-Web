import { expect, test, type Page } from "@playwright/test";

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));
}

// No restore here: it would replace the shared ta_e2e database under every other spec.
test("an admin downloads a backup named with the date", async ({ page }) => {
  await signIn(page);
  await page.goto("/admin");
  const form = page.getByRole("form", { name: "Download a backup" });
  const passphrase = "e2e-backup-passphrase";
  await form.getByLabel("Passphrase", { exact: true }).fill(passphrase);
  await form.getByLabel("Repeat passphrase").fill(passphrase);
  const download = page.waitForEvent("download");
  await form.getByRole("button", { name: "Download backup" }).click();
  expect((await download).suggestedFilename()).toMatch(/^ta-backup-\d{4}-\d{2}-\d{2}\.zip$/);
});

test("the form refuses a mismatch before anything is sent", async ({ page }) => {
  await signIn(page);
  await page.goto("/admin");
  const form = page.getByRole("form", { name: "Download a backup" });
  await form.getByLabel("Passphrase", { exact: true }).fill("e2e-backup-passphrase");
  await form.getByLabel("Repeat passphrase").fill("e2e-backup-passphrase-2");
  await expect(form.getByRole("button", { name: "Download backup" })).toBeDisabled();
  await expect(form.getByRole("alert")).toHaveText("The passphrases do not match.");
});
