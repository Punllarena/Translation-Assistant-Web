import { expect, test, type Page } from "@playwright/test";

const ACTIVE = /\/api\/jobs\?active=true$/;

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));
}

test("the header lists running jobs with a link to each", async ({ page }) => {
  await page.route(ACTIVE, (r) => r.fulfill({ json: [{
    id: 501, kind: "tadb_import", state: "running", progress: 10, total: 100, message: "Checking lines",
    params: { upload_id: "x", dry_run: true, force: false }, result: null,
    created_at: new Date().toISOString(), started_at: new Date().toISOString(), finished_at: null,
  }] }));
  await signIn(page);
  await page.getByRole("button", { name: "1 running" }).click();
  const list = page.locator("#running-jobs");
  await expect(list.getByText("Desktop library import")).toBeVisible();
  await expect(list.getByText("Checking lines · 10 of 100 (10%)")).toBeVisible();
  await list.getByRole("link", { name: "Open" }).click();
  await expect(page).toHaveURL(/\/import$/);
});

test("the header shows nothing while no job runs", async ({ page }) => {
  await page.route(ACTIVE, (r) => r.fulfill({ json: [] }));
  await signIn(page);
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
  await expect(page.getByRole("button", { name: /running/ })).toHaveCount(0);
});
