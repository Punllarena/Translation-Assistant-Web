import { expect, test } from "@playwright/test";
import http from "node:http";
import type { AddressInfo } from "node:net";

const received: Record<string, unknown>[] = [];
let server: http.Server;
let site = "";

test.beforeAll(async () => {
  server = http.createServer((req, res) => {
    const reply = (body: unknown) => { res.setHeader("Content-Type", "application/json"); res.end(JSON.stringify(body)); };
    if (req.url?.startsWith("/wp-json/ta-publisher/v1/status")) return reply({ status: "not_found", post_url: null });
    let raw = "";
    req.on("data", (c) => (raw += c));
    req.on("end", () => {
      received.push(JSON.parse(raw));
      reply({ created: true, updated: false, page_url: `${site}/e2e-publish/e2e-publish-c1/`, post_url: `${site}/post/1/` });
    });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  site = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
});
test.afterAll(() => new Promise<void>((resolve) => server.close(() => resolve())));

test("configure WordPress, publish a chapter, see the badge", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));

  await page.getByRole("link", { name: "WordPress" }).click();
  await page.getByLabel("WordPress endpoint URL").fill(site);
  await page.getByLabel("WordPress API key").fill("e2e-plugin-key");
  await page.getByRole("button", { name: "Save connection" }).click();
  await expect(page.getByText(/Key saved/)).toBeVisible();
  await page.getByRole("button", { name: "Test connection" }).click();
  await expect(page.getByText("Connected; WordPress accepted the API key.")).toBeVisible();

  await page.getByRole("link", { name: "Library" }).click();
  const row = page.getByRole("row").filter({ hasText: "Publish one" });
  await row.getByRole("button", { name: "Publish…" }).click();
  const dialog = page.getByRole("dialog", { name: "Publish to WordPress" });
  await expect(dialog.getByText("WP status: Not published")).toBeVisible();
  await dialog.getByRole("button", { name: "Publish", exact: true }).click();
  await expect(dialog.getByText("Published!")).toBeVisible();
  await dialog.getByRole("button", { name: "Close" }).click();
  await expect(row.getByText(/^pub /)).toBeVisible();
  expect(received.at(-1)).toMatchObject({ series_slug: "e2e-publish", chapter_title: "E2EP Publish one", chapter_index: 1 });
});
