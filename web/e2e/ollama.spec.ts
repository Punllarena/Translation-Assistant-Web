import { expect, test, type Page } from "@playwright/test";
import { openChapter } from "./fixtures/library";

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));
}

test("the Ollama card shows the saved suggestion with its reasoning and stats", async ({ page }) => {
  await signIn(page);
  // The card only shows once Ollama is an enabled backend (the default is MeCab and JParser).
  await page.request.put("/api/settings", { data: { mt_enabled: ["mecab", "jparser", "ollama"] } });
  await openChapter(page, "E2E ollama series", "Ollama target");
  const card = page.getByRole("region", { name: "Ollama" });
  await expect(card).toContainText("She laughed.");
  await expect(card).toContainText("qwen3:14b");
  await expect(card).toContainText("prepared");
  await card.getByRole("button", { name: "Reasoning" }).click();
  const dialog = page.getByRole("dialog", { name: "Ollama reasoning" });
  await expect(dialog.getByText("Because the subject is she")).toBeVisible();
  await dialog.getByRole("tab", { name: "Stats" }).click();
  await expect(dialog).toContainText("412");
});

test("Run now with no Ollama URL shows the setup message", async ({ page }) => {
  await signIn(page);
  await page.goto("/jobs?tab=ollama");
  await expect(page.getByText("E2E ollama series")).toBeVisible();
  await page.getByRole("button", { name: "Run now" }).click();
  await expect(page.getByRole("alert")).toContainText("Set an Ollama URL under Settings → Machine translation.");
});

test("the Ollama statistics tab shows tokens per second", async ({ page }) => {
  await signIn(page);
  await page.goto("/stats?tab=ollama");
  await expect(page.getByText("Tokens/s, 30 days")).toBeVisible();
  await expect(page.getByRole("region", { name: /Tokens per second, 30 days: [1-9]/ })).toBeVisible();
});
