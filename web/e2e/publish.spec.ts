import { expect, test, type Page } from "@playwright/test";
import http from "node:http";
import type { AddressInfo } from "node:net";

const received: Record<string, unknown>[] = [];
let server: http.Server;
let site = "";
// While set, the fake WordPress holds a batch target's publish until it is called, so a test can
// close the dialog while the job is still running.
let hold: Promise<void> | null = null;

test.beforeAll(async () => {
  server = http.createServer((req, res) => {
    const reply = (body: unknown) => { res.setHeader("Content-Type", "application/json"); res.end(JSON.stringify(body)); };
    if (req.url?.startsWith("/wp-json/ta-publisher/v1/status")) return reply({ status: "not_found", post_url: null });
    let raw = "";
    req.on("data", (c) => (raw += c));
    req.on("end", async () => {
      const body = JSON.parse(raw);
      received.push(body);
      if (hold && String(body.chapter_title).includes("Batch target")) await hold;
      reply({ created: true, updated: false, page_url: `${site}/e2e-publish/e2e-publish-c1/`, post_url: `${site}/post/1/` });
    });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  site = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
});
test.afterAll(() => new Promise<void>((resolve) => server.close(() => resolve())));

async function signInAndConnect(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));

  // The connection form remounts when the saved credential arrives, dropping anything typed before it.
  const loaded = page.waitForResponse((r) => new URL(r.url()).pathname === "/api/credentials");
  await page.goto("/settings/wp"); // not via "/", which resumes the last open chapter after a late redirect
  await loaded;
  await page.getByLabel("WordPress endpoint URL").fill(site);
  await page.getByLabel("WordPress API key").fill("e2e-plugin-key");
  await page.getByRole("button", { name: "Save connection" }).click();
  // "Key saved" is already showing when an earlier run saved a key; "Saved" only follows this save.
  await expect(page.getByRole("status").getByText("Saved", { exact: true })).toBeVisible();
  await expect(page.getByText(/Key saved/)).toBeVisible();
  await page.getByRole("button", { name: "Test connection" }).click();
  await expect(page.getByText("Connected; WordPress accepted the API key.")).toBeVisible();
}

test("configure WordPress, publish a chapter, see the badge", async ({ page }) => {
  await signInAndConnect(page);
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

test("batch publish: closing and reopening the dialog never errors, and the chapter ends up published", async ({ page }) => {
  await signInAndConnect(page);
  await page.getByRole("link", { name: "Library" }).click();
  const row = page.getByRole("row").filter({ hasText: "Batch target" });
  await row.getByLabel("Select Batch target").check();
  const open = () => page.getByRole("button", { name: "Publish 1", exact: true }).click();
  let release = () => {};
  hold = new Promise<void>((resolve) => (release = resolve));
  try {
    await open();
    const dialog = page.getByRole("dialog", { name: "Publish / Schedule Chapters" });
    await dialog.getByRole("checkbox", { name: /Schedule \(unchecked/ }).uncheck();
    await dialog.getByRole("checkbox", { name: /^Overwrite/ }).check(); // so a rerun publishes it again
    await dialog.getByRole("button", { name: "Start" }).click();
    await expect(dialog.getByRole("progressbar")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await open();
    // The job is still running: the reopened dialog follows it rather than offering a second batch (a 409).
    await expect(dialog.getByRole("progressbar")).toBeVisible();
    await expect(dialog.getByRole("alert")).toHaveCount(0);
    await dialog.getByRole("button", { name: "Close" }).click();
    await expect(dialog).toBeHidden();
  } finally {
    hold = null;
    release();
  }
  // The job finishes after the dialog is gone; the row still has to pick that up.
  await expect(row.getByText(/^pub /)).toBeVisible();
});
