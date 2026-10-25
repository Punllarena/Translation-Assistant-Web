import { expect, test, type Page } from "@playwright/test";

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
}

async function resetPrefs(page: Page) {
  await page.evaluate(() => {
    localStorage.removeItem("ta.librarySort");
    localStorage.removeItem("ta.libraryFilters");
  });
}

const DROPPED = "Filter spec dropped";
const ONGOING = "Filter spec ongoing";
const link = (page: Page, title: string) => page.getByRole("link", { name: title, exact: true });
const filtersPanel = (page: Page) => page.getByRole("group", { name: "Library filters" });

test("archive hides a series, Archived → Include finds it, Unarchive brings it back", async ({ page }) => {
  await signIn(page);
  try {
    await page.goto("/");
    await link(page, DROPPED).click();
    await page.getByRole("tab", { name: "Settings" }).click();
    await page.getByRole("button", { name: "Archive series" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Archive series" }).click();
    await expect(page.getByRole("dialog")).toBeHidden();

    await page.goto("/");
    await expect(link(page, ONGOING)).toBeVisible();
    await expect(link(page, DROPPED)).toHaveCount(0);

    await page.getByRole("button", { name: /^Filters/ }).click();
    await filtersPanel(page).getByRole("group", { name: "Archived" }).getByLabel("Include").check();
    await page.keyboard.press("Escape");
    await expect(page.getByText("Archived: Include")).toBeVisible();
    await expect(link(page, DROPPED)).toBeVisible();

    await link(page, DROPPED).click();
    await page.getByRole("button", { name: "Unarchive", exact: true }).click();
    await expect(page.getByRole("button", { name: "Unarchive", exact: true })).toHaveCount(0);

    await resetPrefs(page);
    await page.goto("/");
    await expect(link(page, DROPPED)).toBeVisible();
  } finally {
    await page.goto("/");
    await resetPrefs(page);
  }
});

test("status filter and its chip", async ({ page }) => {
  await signIn(page);
  await page.goto("/");
  try {
    await page.getByRole("button", { name: /^Filters/ }).click();
    await filtersPanel(page).getByRole("group", { name: "Status" }).getByLabel("Dropped").check();
    await page.keyboard.press("Escape");
    await expect(page.getByText("Status: Dropped")).toBeVisible();
    await expect(link(page, DROPPED)).toBeVisible();
    await expect(link(page, ONGOING)).toHaveCount(0);

    await page.reload();
    await expect(page.getByText("Status: Dropped")).toBeVisible();
    await expect(link(page, ONGOING)).toHaveCount(0);

    await page.getByRole("button", { name: "Remove Status filter" }).click();
    await expect(link(page, DROPPED)).toBeVisible();
    await expect(link(page, ONGOING)).toBeVisible();
  } finally {
    await resetPrefs(page);
  }
});

test("title sort orders A–Z", async ({ page }) => {
  await signIn(page);
  await page.goto("/");
  try {
    await page.getByLabel("Sort by").selectOption({ label: "Title" });
    const texts = await page.getByRole("link", { name: /Filter spec (dropped|ongoing)/ }).allTextContents();
    const names = texts.map((t) => t.match(/Filter spec (dropped|ongoing)/)?.[0]);
    expect(names.indexOf(DROPPED)).toBeGreaterThanOrEqual(0);
    expect(names.indexOf(DROPPED)).toBeLessThan(names.indexOf(ONGOING));
  } finally {
    await resetPrefs(page);
  }
});
