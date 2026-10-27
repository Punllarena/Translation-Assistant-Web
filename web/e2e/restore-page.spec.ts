import { expect, test } from "@playwright/test";

function status(phase: "restoring" | "done" | "failed", extra: object = {}) {
  return { phase, done: 3, total: 10, message: "lines", error: null, ...extra };
}

// The restore page must render and poll while every other route answers 503.
// (A path predicate, not "**/api/**": that also matches Vite's /src/api/client.ts module.)
const isApi = (url: URL) => url.pathname.startsWith("/api/");

test("the progress page survives maintenance and ends on sign in", async ({ page }) => {
  let calls = 0;
  await page.route(isApi, (route) => {
    if (new URL(route.request().url()).pathname === "/api/restore/status") {
      calls += 1;
      return route.fulfill({ json: status(calls <= 2 ? "restoring" : "done") });
    }
    return route.fulfill({ status: 503, json: { detail: "Restore in progress" } });
  });

  await page.goto("/restore");

  await expect(page.getByRole("progressbar")).toBeVisible();
  await expect(page.getByText("3 of 10")).toBeVisible();
  await expect(page.getByText("Restore finished. Sign in with an account from the backup."))
    .toBeVisible();
  await page.getByRole("link", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/login$/);
});

test("a failed restore says the server was not changed", async ({ page }) => {
  await page.route(isApi, (route) =>
    new URL(route.request().url()).pathname === "/api/restore/status"
      ? route.fulfill({
        json: status("failed", { error: "The restore failed; the server was not changed." }),
      })
      : route.fulfill({ status: 503, json: { detail: "Restore in progress" } }),
  );

  await page.goto("/restore");

  await expect(page.getByRole("alert")).toHaveText("The restore failed; the server was not changed.");
  await expect(page.getByText("The server was not changed.", { exact: true })).toBeVisible();
});
