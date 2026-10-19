import { expect, test } from "@playwright/test";

test("the setup wizard creates the admin and every later step can be skipped", async ({ page }) => {
  let claimed = false;
  await page.route("**/api/setup/status", (r) => r.fulfill({ json: { needs_setup: !claimed } }));
  await page.route("**/api/setup/admin", async (r) => {
    const login = await page.request.post("/api/auth/login", { data: { login: "e2e@example.com", password: "e2e-password-123" } });
    claimed = true;
    await r.fulfill({ status: 201, json: await login.json() });
  });
  await page.goto("/stats");
  await expect(page).toHaveURL(/\/setup$/);
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Username").fill("e2e_admin");
  await page.getByLabel("Password", { exact: true }).fill("e2e-password-123");
  await page.getByLabel("Repeat password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Create admin" }).click();
  for (const heading of ["Server settings", "Dictionary", "Desktop library"]) {
    await expect(page.getByRole("heading", { name: heading, level: 2 }).first()).toBeVisible();
    await page.getByRole("button", { name: "Skip" }).click();
  }
  await page.getByRole("link", { name: "Open the library" }).click();
  await expect(page).toHaveURL(/\/$/);
});

test("mismatched passwords are caught before anything is sent", async ({ page }) => {
  await page.route("**/api/setup/status", (r) => r.fulfill({ json: { needs_setup: true } }));
  await page.goto("/setup");
  await page.getByLabel("Email").fill("x@example.com");
  await page.getByLabel("Username").fill("x_admin");
  await page.getByLabel("Password", { exact: true }).fill("first-password-1");
  await page.getByLabel("Repeat password").fill("other-password-1");
  await page.getByRole("button", { name: "Create admin" }).click();
  await expect(page.getByRole("alert")).toHaveText("The passwords do not match.");
});

test("a lost setup race points to sign in", async ({ page }) => {
  const message = "Setup is already complete; sign in instead.";
  await page.route("**/api/setup/status", (r) => r.fulfill({ json: { needs_setup: true } }));
  await page.route("**/api/setup/admin", (r) => r.fulfill({ status: 409, json: { detail: message } }));
  await page.goto("/setup");
  await page.getByLabel("Email").fill("x@example.com");
  await page.getByLabel("Username").fill("x_admin");
  await page.getByLabel("Password", { exact: true }).fill("first-password-1");
  await page.getByLabel("Repeat password").fill("first-password-1");
  await page.getByRole("button", { name: "Create admin" }).click();
  await expect(page.getByRole("alert")).toContainText(message);
  await page.getByRole("link", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/login$/);
});
