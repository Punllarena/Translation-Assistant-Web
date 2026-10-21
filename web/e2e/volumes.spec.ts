import { expect, test, type Page } from "@playwright/test";
import { openSeries } from "./fixtures/library";

// These tests run in order and build on each other: the series is seeded once per run.

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
}

const SERIES = "E2E volume naming series";
const titles = (page: Page) => page.locator(".vol-list .vol-title");
const isOrderRequest = (r: { url(): string; method(): string }) =>
  r.method() === "PUT" && r.url().includes("/volumes/order");

test.describe.configure({ mode: "serial" });

test("editing an index moves the volume", async ({ page }) => {
  await signIn(page);
  await openSeries(page, SERIES);
  await expect(titles(page)).toHaveText(["Volume 1", "Volume 2", "Volume 3"]);
  await page.getByRole("button", { name: /^Volume 3/ }).click();
  await page.getByRole("button", { name: "Volume actions" }).click();
  await page.getByRole("menuitem", { name: "Edit volume details" }).click();
  const dialog = page.getByRole("dialog", { name: "Volume details" });
  await dialog.getByLabel("Number").fill("1.5");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog).toBeHidden();
  await expect(titles(page)).toHaveText(["Volume 1", "Volume 1.5", "Volume 2"]);
});

test("a dragged volume keeps its place", async ({ page }) => {
  await signIn(page);
  await openSeries(page, SERIES);
  await page.locator(".vol-row").filter({ has: page.locator(".vol-title", { hasText: /^Volume 1$/ }) }).locator(".grip")
    .dragTo(page.getByRole("button", { name: /^Volume 2\b/ }));
  await expect(titles(page)).toHaveText(["Volume 1.5", "Volume 2", "Volume 1"]);
  await page.getByRole("button", { name: "New volume" }).click();
  const dialog = page.getByRole("dialog", { name: "New volume" });
  await expect(dialog.getByLabel("Number")).toHaveValue("3");
  await dialog.getByRole("button", { name: "Create" }).click();
  await expect(dialog).toBeHidden();
  await expect(titles(page)).toHaveText(["Volume 1.5", "Volume 2", "Volume 1", "Volume 3"]);
});

test("Sort by number restores order", async ({ page }) => {
  await signIn(page);
  await openSeries(page, SERIES);
  await page.getByRole("button", { name: "Volume actions" }).click();
  await page.getByRole("menuitem", { name: "Sort volumes by number" }).click();
  const dialog = page.getByRole("dialog", { name: "Sort volumes by number" });
  await expect(dialog.getByText("Sort volumes by kind and number? Volumes you placed by hand will move.")).toBeVisible();
  await dialog.getByRole("button", { name: "Sort", exact: true }).click();
  await expect(dialog).toBeHidden();
  await expect(titles(page)).toHaveText(["Volume 1", "Volume 1.5", "Volume 2", "Volume 3"]);
});

test("a chapter can still be dropped on a volume", async ({ page }) => {
  await signIn(page);
  await openSeries(page, SERIES);
  const orderRequests: string[] = [];
  page.on("request", (r) => { if (isOrderRequest(r)) orderRequests.push(r.url()); });
  await page.getByRole("button", { name: /^Volume 1\b(?!\.)/ }).click();
  await expect(page.getByRole("link", { name: "Open Naming chapter 1" })).toBeVisible();
  await page.getByRole("row").filter({ hasText: "Naming chapter 1" }).locator(".grip")
    .dragTo(page.getByRole("button", { name: /^Volume 2\b/ }));
  await expect(page.getByRole("link", { name: "Open Naming chapter 1" })).toBeHidden();
  await page.getByRole("button", { name: /^Volume 2\b/ }).click();
  await expect(page.getByRole("link", { name: "Open Naming chapter 1" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Open Naming chapter 2" })).toBeVisible();
  expect(orderRequests).toEqual([]);
});
