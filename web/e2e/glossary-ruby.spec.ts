import { expect, test, type Page } from "@playwright/test";
import { openChapter } from "./fixtures/library";

async function open(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
  await openChapter(page, "E2E glossary ruby series", "Ruby target");
}

/** The glossary_ruby setting as the server holds it (saveSetting writes it fire-and-forget). */
function serverGlossaryRuby(page: Page): Promise<unknown> {
  return page.evaluate(async () => (await (await fetch("/api/settings")).json()).glossary_ruby);
}

/** Put the account's glossary ruby and reading aid back to their defaults, so no other spec sees them on. */
async function reset(page: Page) {
  await page.evaluate(() => fetch("/api/settings", {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ glossary_ruby: false, reading_aid: "off" }),
  }));
}

test("the toggle shows the original with the glossary on top", async ({ page }) => {
  try {
    await open(page);
    // off (default): the glossary-replaced text, no glossary ruby
    await expect(page.locator("p.source")).toContainText("Tokyoです。");
    await expect(page.locator("p.source rt.rt-glossary")).toHaveCount(0);

    await page.getByRole("button", { name: "Glossary ruby" }).click();
    await expect(page.getByRole("button", { name: "Glossary ruby" })).toHaveAttribute("aria-pressed", "true");
    await expect.poll(() => serverGlossaryRuby(page)).toBe(true);

    // the setting persists across a reload, and on it the original text carries the
    // translation as ruby over the phrase
    await page.reload();
    await expect(page.getByRole("button", { name: "Glossary ruby" })).toHaveAttribute("aria-pressed", "true");
    const ruby = page.locator("p.source ruby", { hasText: "東京" });
    await expect(ruby.locator("rt")).toHaveText("Tokyo");
    await expect(ruby.locator("rt")).toHaveClass(/rt-glossary/);
    await expect(ruby.locator("span")).toHaveText("東京");
  } finally {
    await reset(page);
  }
});

test("glossary ruby wins over the reading on the active card", async ({ page }) => {
  try {
    await open(page);
    const status = await page.evaluate(async () => {
      const r = await fetch("/api/readings", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: "東京" }),
      });
      return r.ok ? await r.json() : null;
    });
    test.skip(!status || status.available === false, "MeCab is not installed");
    // Turn both on through the API, then reload, so the rendered state is clean.
    await page.evaluate(() => fetch("/api/settings", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ glossary_ruby: true, reading_aid: "hiragana" }),
    }));
    await page.reload();
    await expect(page.getByRole("button", { name: "Glossary ruby" })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("button", { name: "Hiragana readings" })).toHaveAttribute("aria-pressed", "true");
    const ruby = page.locator("p.source ruby", { hasText: "東京" });
    await expect(ruby.locator("rt")).toHaveText("Tokyo"); // the glossary wins over the reading
    await expect(ruby.locator("rt")).toHaveClass(/rt-glossary/);
    await expect(page.locator("p.source rt")).toHaveCount(1); // no reading over the phrase
  } finally {
    await reset(page);
  }
});
