import { expect, test, type Page } from "@playwright/test";

// The whole settings page: /settings/editor lands first, then every sidebar entry opens its section.
const SECTIONS = [
  { link: "Editor", path: "/settings/editor", heading: "Editor" },
  { link: "Machine translation", path: "/settings/mt", heading: "Machine translation" },
  { link: "WordPress", path: "/settings/wp", heading: "WordPress" },
  { link: "Shortcuts", path: "/settings/shortcuts", heading: "Keyboard shortcuts" },
  { link: "Server", path: "/settings/admin/server", heading: "Server" },
  { link: "Invites", path: "/settings/admin/invites", heading: "Invites" },
  { link: "Dictionary", path: "/settings/admin/dictionary", heading: "Dictionary" },
  { link: "Backup & restore", path: "/settings/admin/backup", heading: "Backup & restore" },
];

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));
}

test("each sidebar entry opens its section", async ({ page }) => {
  await signIn(page);
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Settings" }).click();
  await expect(page).toHaveURL(/\/settings\/editor$/);
  const nav = page.getByRole("navigation", { name: "Settings" });
  const header = page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Settings" });
  for (const section of SECTIONS) {
    const entry = nav.getByRole("link", { name: section.link, exact: true });
    await entry.click();
    await expect(page).toHaveURL(new RegExp(`${section.path}$`));
    await expect(page.getByRole("heading", { level: 1, name: section.heading })).toBeVisible();
    await expect(entry).toHaveAttribute("aria-current", "page");
    await expect(header).toHaveAttribute("aria-current", "page");
  }
});

test("old URLs land in the sidebar", async ({ page }) => {
  await signIn(page);
  await page.goto("/settings");
  await expect(page).toHaveURL(/\/settings\/editor$/);
  await expect(page.getByRole("heading", { level: 1, name: "Editor" })).toBeVisible();
  // replace, not push: Back leaves Settings instead of bouncing through the redirect again
  await page.goBack();
  await expect(page).not.toHaveURL(/\/settings(\/|$)/);

  await page.goto("/admin");
  await expect(page).toHaveURL(/\/settings\/admin\/server$/);
  await expect(page.getByRole("heading", { level: 1, name: "Server" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Settings" }).getByRole("link", { name: "Server" }))
    .toHaveAttribute("aria-current", "page");
});

test("a non-admin sees no Admin group", async ({ page }) => {
  await signIn(page);
  // The seed has one admin account: answer /auth/me as a member instead of creating another.
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({ json: { id: 1, email: "e2e@example.com", username: "e2e", is_admin: false } }));
  const adminCalls: string[] = [];
  page.on("request", (r) => { if (r.url().includes("/api/admin/")) adminCalls.push(r.url()); });

  await page.goto("/settings/editor");
  const nav = page.getByRole("navigation", { name: "Settings" });
  await expect(nav.getByRole("link", { name: "Editor" })).toBeVisible();
  await expect(nav.getByText("Admin", { exact: true })).toHaveCount(0);
  await expect(nav.getByRole("link", { name: "Server" })).toHaveCount(0);

  await page.goto("/settings/admin/server");
  await expect(page.getByText("Admin only.")).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Settings" })).toBeVisible();
  expect(adminCalls).toEqual([]);
});
