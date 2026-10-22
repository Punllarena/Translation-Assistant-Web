import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";

const here = path.dirname(fileURLToPath(import.meta.url));

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
}

test("New series offers three sources", async ({ page }) => {
  await signIn(page);
  await page.goto("/");
  await page.getByRole("link", { name: "New series" }).first().click();
  await expect(page).toHaveURL(/\/new$/);
  await expect(page.getByRole("button", { name: /Syosetu/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /EPUB/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Paste/ })).toBeVisible();
});

test("Paste creates an empty series with credits", async ({ page }) => {
  await signIn(page);
  await page.goto("/new");
  await page.getByRole("button", { name: /Paste/ }).click();
  await page.getByLabel("Title", { exact: true }).fill("NS Paste");
  await page.getByLabel("Japanese title").fill("貼り付け");
  await page.getByLabel("Author (romaji)").fill("Harituke");
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page).toHaveURL(/\/series\/\d+/);
  await page.getByRole("tab", { name: "Settings" }).click();
  await expect(page.getByLabel("Japanese title")).toHaveValue("貼り付け");
});

test("A taken paste title is refused", async ({ page }) => {
  await signIn(page);
  const made = await page.request.post("/api/series", { data: { title: "NS Paste Taken", syosetu_url: "" } });
  expect(made.ok()).toBeTruthy();
  await page.goto("/new?source=paste");
  await page.getByLabel("Title", { exact: true }).fill("NS Paste Taken");
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("alert")).toContainText("a series with that title exists");
});

test("EPUB creates a series and volume", async ({ page }) => {
  await signIn(page);
  await page.goto("/new?source=epub");
  await page.getByLabel("EPUB file").setInputFiles(path.join(here, "fixtures/sample.epub"));
  await expect(page.getByLabel("Japanese title")).not.toHaveValue("");
  await page.getByLabel("Title", { exact: true }).fill("NS Epub");
  await page.getByLabel("Author (romaji)").fill("Romaji Name");
  await expect(page.getByLabel("Author", { exact: true }).last()).toHaveValue("Romaji Name");
  for (const box of await page.getByRole("checkbox").all()) await box.check();
  await page.getByRole("button", { name: "Import", exact: true }).click();
  await expect(page.getByText("Import complete.")).toBeVisible();
  await page.getByRole("link", { name: "Open series" }).click();
  await expect(page).toHaveURL(/\/series\/\d+/);
  await expect(page.getByText("Neko chapter").first()).toBeVisible();
});

test("EPUB refuses a taken title", async ({ page }) => {
  await signIn(page);
  const made = await page.request.post("/api/series", { data: { title: "NS Epub Taken", syosetu_url: "" } });
  expect(made.ok()).toBeTruthy();
  await page.goto("/new?source=epub");
  await page.getByLabel("EPUB file").setInputFiles(path.join(here, "fixtures/sample.epub"));
  await expect(page.getByLabel("Japanese title")).not.toHaveValue("");
  await page.getByLabel("Title", { exact: true }).fill("NS Epub Taken");
  for (const box of await page.getByRole("checkbox").all()) await box.check();
  await page.getByRole("button", { name: "Import", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("a series with that title exists");
});

test("Syosetu reads the novel and prefills", async ({ page }) => {
  await signIn(page);
  await page.route("**/api/scrape/syosetu/novel", (route) => route.fulfill({
    json: { title: "勇者の旅", author: "山田太郎", short_story: false, first_chapter: { num: 1, title: "第一話" } },
  }));
  await page.route("**/api/series/*/syosetu/fetch", (route) => route.fulfill({ status: 500, json: { detail: "boom" } }));
  await page.goto("/new?source=syosetu");
  await page.getByLabel("Syosetu URL").fill("https://ncode.syosetu.com/n9999zz/");
  await page.getByRole("button", { name: "Read" }).click();
  await expect(page.getByLabel("Japanese title")).toHaveValue("勇者の旅");
  await expect(page.getByLabel("Author", { exact: true })).toHaveValue("山田太郎");
  await expect(page.getByText("Chapter 1: 第一話 will be fetched.")).toBeVisible();
  await page.getByLabel("Title", { exact: true }).fill("NS Syosetu");
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page).toHaveURL(/\/series\/\d+\?tab=tools/);
  await expect(page.getByRole("alert").filter({ hasText: "Use Fetch from Syosetu below to try again." })).toContainText("boom");
});
