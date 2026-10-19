import path from "node:path";
import { expect, test } from "@playwright/test";

test("a user imports a desktop ta.db after reading the dry run", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("tadb@example.com");
  await page.getByLabel("Password").fill("tadb-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));
  await page.goto("/import");
  await page.getByLabel("Desktop ta.db").setInputFiles(path.resolve(import.meta.dirname, ".generated/ta.db"));
  const card = page.getByRole("region", { name: "Desktop library (ta.db)" });
  await expect(card.getByRole("columnheader", { name: "Would add" })).toBeVisible();
  await card.getByRole("button", { name: "Import", exact: true }).click();
  await expect(card.getByText("Imported.")).toBeVisible();
  await page.goto("/");
  await expect(page.getByRole("link", { name: "My Series" })).toBeVisible();
});

const signIn = async (page: import("@playwright/test").Page) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("tadb@example.com");
  await page.getByLabel("Password").fill("tadb-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));
};

const pendingJob = (state: string, dry: boolean, result: object | null = null) => ({
  id: 9001, kind: "tadb_import", state, progress: 71330, total: 482456, message: "Checking lines",
  params: { upload_id: "0123456789abcdef0123456789abcdef", dry_run: dry, force: false }, result,
  created_at: new Date().toISOString(), started_at: new Date(Date.now() - 7 * 60_000).toISOString(), finished_at: null,
});

test("the import card restores a finished dry run", async ({ page }) => {
  const result = { dry_run: true, refused: null, written: { documents: 3 }, skipped: {}, already_present: {}, messages: [] };
  await page.route("**/api/import/tadb/pending", (r) => r.fulfill({ json: { job: pendingJob("done", true, result), upload_id: "0123456789abcdef0123456789abcdef" } }));
  await signIn(page);
  await page.goto("/import");
  const card = page.getByRole("region", { name: "Desktop library (ta.db)" });
  await expect(card.getByRole("columnheader", { name: "Would add" })).toBeVisible();
  await expect(card.getByRole("button", { name: "Import", exact: true })).toBeVisible();
});

test("the import card follows a running import with counts and Cancel", async ({ page }) => {
  const job = pendingJob("running", true);
  await page.addInitScript((j) => {
    // One running update, then the stream stays open (a fulfilled route would close it).
    class OpenSource {
      private listener?: (e: { data: string }) => void;
      onerror: (() => void) | null = null;
      constructor() { setTimeout(() => this.listener?.({ data: JSON.stringify(j) }), 50); }
      addEventListener(_type: string, fn: (e: { data: string }) => void) { this.listener = fn; }
      close() {}
    }
    (window as unknown as { EventSource: unknown }).EventSource = OpenSource;
  }, job);
  await page.route("**/api/import/tadb/pending", (r) => r.fulfill({ json: { job, upload_id: job.params.upload_id } }));
  await signIn(page);
  await page.goto("/import");
  const card = page.getByRole("region", { name: "Desktop library (ta.db)" });
  await expect(card.getByText("Checking lines · 71,330 of 482,456 (15%)")).toBeVisible();
  await expect(card.getByText(/7 min elapsed/)).toBeVisible();
  await expect(card.getByText("Runs on the server — you can leave this page and come back.")).toBeVisible();
  await expect(card.getByRole("button", { name: "Cancel" })).toBeVisible();
});
