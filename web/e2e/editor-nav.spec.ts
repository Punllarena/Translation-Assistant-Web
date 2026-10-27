import { expect, test, type Page } from "@playwright/test";
import { openChapter } from "./fixtures/library";

async function open(page: Page, chapter: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
  await openChapter(page, "Nav series", chapter);
  await expect(page.getByRole("button", { name: "Next chapter", exact: true })).toBeVisible();
}

const card = (page: Page, index: number) => page.locator(`article[data-index="${index}"]`);

test("chapter arrows and list", async ({ page }) => {
  await open(page, "Nav one");
  const oneUrl = page.url();
  await page.getByRole("button", { name: "Next chapter", exact: true }).click();
  await expect(page.getByText("二話目です。")).toBeVisible();
  expect(page.url()).not.toBe(oneUrl);
  const twoUrl = page.url();
  await page.getByRole("button", { name: "Previous chapter", exact: true }).click();
  await expect(page.getByText("今日は晴れ。")).toBeVisible();
  expect(page.url()).toBe(oneUrl);
  await page.getByRole("button", { name: /, chapter list$/ }).click();
  await page.getByRole("menuitemradio", { name: /^2 · Nav two/ }).click();
  await expect(page.getByText("二話目です。")).toBeVisible();
  expect(page.url()).toBe(twoUrl);
});

test("failed save stops the move", async ({ page }) => {
  await open(page, "Nav one");
  await page.route("**/documents/*/lines", (r) =>
    r.request().method() === "PATCH" ? r.fulfill({ status: 500 }) : r.continue());
  const oneUrl = page.url();
  await page.getByRole("textbox", { name: "Translation" }).click();
  await page.keyboard.type("Unsaved words.");
  await page.getByRole("button", { name: "Next chapter", exact: true }).click();
  await expect(page.getByText("Not moved: the last changes are not saved yet")).toBeVisible({ timeout: 10_000 });
  expect(page.url()).toBe(oneUrl);
});

test("author ruby always shows", async ({ page }) => {
  await open(page, "Nav one");
  await page.getByRole("button", { name: "Readings off" }).click();
  const big = card(page, 0).locator("ruby", { hasText: "大" });
  await expect(big.locator("rt")).toHaveText("おお");
  await expect(big.locator("rp").first()).not.toBeVisible();
  await expect(card(page, 1).locator("ruby", { hasText: "STATUS" }).locator("rt")).toHaveText("ステータス");
});

test("reading aid on the active card", async ({ page }) => {
  await open(page, "Nav one");
  const status = await page.evaluate(async () => {
    const r = await fetch("/api/readings", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: "今日" }),
    });
    return r.ok ? await r.json() : null;
  });
  test.skip(!status || status.available === false, "MeCab is not installed");
  await card(page, 2).click();
  await page.getByRole("button", { name: "Hiragana readings" }).click();
  const today = card(page, 2).locator("ruby", { hasText: "今日" });
  await expect(today.locator("rt")).toHaveText("きょう");
  // a non-active card carries only its author ruby
  await expect(card(page, 3).locator("rt")).toHaveCount(0);
  await expect(card(page, 0).locator("rt")).toHaveCount(2);
  await page.getByRole("button", { name: "Romaji readings" }).click();
  await expect(card(page, 2).locator("ruby", { hasText: "今日" }).locator("rt")).toHaveText("kyō");
  await page.getByRole("button", { name: "Readings off" }).click();
});

test("jump back", async ({ page }) => {
  await open(page, "Nav one");
  // line 1 translated and still active, so the next untranslated line is line 2 (a separate button)
  await card(page, 0).click();
  await card(page, 0).getByRole("textbox", { name: "Translation" }).click();
  await page.keyboard.type("One.");
  await card(page, 22).scrollIntoViewIfNeeded();
  await expect(page.getByRole("button", { name: "Back to editing · line 1" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Next untranslated · line 2" })).toBeVisible();
  await page.getByRole("button", { name: "Back to editing · line 1" }).click();
  await expect(card(page, 0)).toBeInViewport();
});

test("end card", async ({ page }) => {
  await open(page, "Nav two");
  await page.getByRole("textbox", { name: "Translation" }).click();
  await page.keyboard.type("The second story.");
  await expect(page.getByText("Saved", { exact: true })).toBeVisible({ timeout: 5_000 });
  await expect(page.getByText(/All 1 lines translated/)).toBeVisible();
  await expect(page.getByText("Last chapter of the series")).toBeVisible();
  await expect(page.getByRole("link", { name: /^Next chapter →/ })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Back to series" })).toBeVisible();
});
