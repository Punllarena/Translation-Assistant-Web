import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { openChapter } from "./fixtures/library";

// The dictionary is server-wide: remove any leftover so retries and other specs see a clean list.
async function cleanup(page: Page) {
  try {
    const res = await page.request.get("/api/admin/dictionary");
    if (!res.ok()) return;
    const body = (await res.json()) as { yomitan: { id: number; title: string }[] };
    for (const d of body.yomitan.filter((x) => x.title === "E2E Yomitan")) {
      await page.request.delete(`/api/admin/dictionary/yomitan/${d.id}`);
    }
  } catch { /* best effort */ }
}

test.afterEach(async ({ page }) => { await cleanup(page); });

test("an admin uploads a Yomitan dictionary and JParser uses it", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));
  await cleanup(page);
  await page.goto("/admin");
  await page.getByLabel("Upload Yomitan dictionary").setInputFiles(path.resolve(import.meta.dirname, "fixtures/yomitan-e2e.zip"));
  await expect(page.getByRole("status").filter({ hasText: "Installed E2E Yomitan (1 entry)" })).toBeVisible();
  const order = page.getByRole("list", { name: "Dictionary order" });
  const items = order.getByRole("listitem");
  await expect(items.nth(0)).toContainText("EDICT2");
  await expect(items.nth(1)).toContainText("E2E Yomitan");
  await page.getByRole("button", { name: "Move E2E Yomitan up" }).click();
  await expect(items.nth(0)).toContainText("E2E Yomitan");
  await openChapter(page, "Yomitan spec", "Yomitan target");
  await expect(page.getByRole("region", { name: "JParser" })).toContainText("yomitan e2e gloss");
  await page.goto("/admin");
  await page.getByRole("button", { name: "Remove E2E Yomitan" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Remove" }).click();
  await expect(order).not.toContainText("E2E Yomitan");
});
