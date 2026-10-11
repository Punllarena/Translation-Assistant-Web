import { expect, test } from "@playwright/test";

async function openSeries(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
  await page.goto("/");
  await page.getByRole("link", { name: "E2E series", exact: true }).click();
}

test("find and replace across a series", async ({ page }) => {
  await openSeries(page);
  await page.getByLabel("Find in series").fill("Tarou");
  await page.getByLabel("Replace with").fill("Taro");
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.getByText("2 matches")).toBeVisible();
  // the click only resolves once the dialog is handled, so don't await it before accepting
  const dialog = page.waitForEvent("dialog");
  const click = page.getByRole("button", { name: /Replace selected/ }).click();
  await (await dialog).accept();
  await click;
  await expect(page.getByText("Replaced 2")).toBeVisible();
  // the match list clears after a replace, so check the result in the editor
  await page.goto("/");
  await page.getByRole("link", { name: "Open Series one" }).click();
  await expect(page.getByRole("textbox", { name: "Translation" })).toHaveText("Taro came.");
});

test("phrase suggestions: analyze, translate and add a term", async ({ page }) => {
  await openSeries(page);
  await page.getByLabel("Min frequency").fill("2");
  await page.getByRole("button", { name: "Analyze" }).click();
  await expect(page.getByRole("cell", { name: "太郎", exact: true })).toBeVisible();
  await page.getByLabel("Translation for 太郎").fill("Taro");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByRole("cell", { name: "太郎", exact: true })).toHaveCount(0);
});
