import { expect, test } from "@playwright/test";
import { openChapter as openIn } from "./fixtures/library";

async function openChapter(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
  await openIn(page, "E2E tm series", "TM target");
}

test("translation memory offers another chapter's translation and a click fills it", async ({ page }) => {
  await openChapter(page);
  const panel = page.getByRole("complementary", { name: "Translation memory" });
  await expect(panel).toContainText("Memory source");
  await panel.getByRole("button", { name: 'Use "Remembered translation.", Alt+1' }).click();
  await expect(page.getByRole("textbox", { name: "Translation" })).toHaveText("Remembered translation.");
  const toggle = page.getByRole("button", { name: "Translation memory" });
  await expect(toggle).toHaveAttribute("aria-pressed", "true");
  await toggle.click();
  await expect(panel).toHaveCount(0);
  await expect(toggle).toHaveAttribute("aria-pressed", "false");
  await toggle.click();
  await expect(panel).toBeVisible();
  await expect(toggle).toHaveAttribute("aria-pressed", "true");
});

test("Ctrl+Z undoes a Use and brings the earlier translation back", async ({ page }) => {
  await openChapter(page);
  const box = page.getByRole("textbox", { name: "Translation" });
  await box.click();
  await page.keyboard.press("Control+a"); // the test above may have saved a translation here
  await page.keyboard.type("my own draft");
  const panel = page.getByRole("complementary", { name: "Translation memory" });
  await panel.getByRole("button", { name: 'Use "Remembered translation.", Alt+1' }).click();
  await expect(box).toHaveText("Remembered translation.");
  await box.press("Control+z");
  await expect(box).toHaveText("my own draft");
});

test("Ctrl+L adds a glossary phrase and the source updates in place", async ({ page }) => {
  await openChapter(page);
  const box = page.getByRole("textbox", { name: "Translation" });
  await box.click();
  await page.keyboard.type("keep this");
  await page.keyboard.press("Control+l");
  const dialog = page.getByRole("dialog", { name: "Add a glossary phrase" });
  await dialog.getByLabel("Source phrase").fill("記憶語");
  await dialog.getByLabel("Translation").fill("memory word");
  await dialog.getByRole("button", { name: "Add" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByText("Added “記憶語” to the glossary")).toBeVisible();
  // The source line, not the MT panel, which shows the phrase too.
  await expect(page.locator("p.source", { hasText: "memory_word" })).toBeVisible();
  await expect(box).toContainText("keep this");
});
