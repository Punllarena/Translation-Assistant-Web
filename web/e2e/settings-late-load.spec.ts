import { expect, test, type Page } from "@playwright/test";

// A saved credential (or setting) that arrives after the user has started typing must not wipe what they typed.
const saved = (kind: string, endpoint_url: string, id: number) =>
  ({ id, kind, name: "", endpoint_url, has_secret: false, secret_hint: "", secret_unreadable: false });

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
}

async function slowCredentials(page: Page, creds: object[]) {
  await page.route("**/api/credentials", async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    await new Promise((r) => setTimeout(r, 1500));
    await route.fulfill({ json: creds });
  });
}

test("WordPress connection keeps input typed before the saved credential loads", async ({ page }) => {
  await signIn(page);
  await slowCredentials(page, [saved("wordpress", "https://old.example/wp-json/ta-publisher/v1/publish", 9001)]);
  const loaded = page.waitForResponse((r) => r.url().endsWith("/api/credentials"));
  await page.goto("/settings/wp");
  const url = page.getByLabel("WordPress endpoint URL");
  await url.fill("https://typed.example/wp");
  await page.getByLabel("WordPress API key").fill("typed-key");
  await loaded;
  await expect(page.getByText("No key saved")).toBeVisible();
  await expect(url).toHaveValue("https://typed.example/wp");
  await expect(page.getByLabel("WordPress API key")).toHaveValue("typed-key");
});

test("machine translation URLs and Ollama options keep input typed before saved values load", async ({ page }) => {
  await signIn(page);
  await slowCredentials(page, [saved("libretranslate", "https://lt.example", 9002), saved("ollama", "https://ollama.example", 9003)]);
  await page.route("**/api/settings", async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    const res = await route.fetch();
    await new Promise((r) => setTimeout(r, 1500));
    await route.fulfill({ response: res, json: { ...(await res.json()), ollama_model: "saved-model" } });
  });
  const loaded = Promise.all(["/api/credentials", "/api/settings"].map((p) => page.waitForResponse((r) => r.url().endsWith(p))));
  await page.goto("/settings/mt");
  await page.getByLabel("LibreTranslate URL").fill("https://typed-lt.example");
  await page.getByLabel("Ollama URL").fill("https://typed-ollama.example");
  await page.getByLabel("Ollama model").fill("typed-model");
  await loaded;
  await expect(page.getByLabel("LibreTranslate URL")).toHaveValue("https://typed-lt.example");
  await expect(page.getByLabel("Ollama URL")).toHaveValue("https://typed-ollama.example");
  await expect(page.getByLabel("Ollama model")).toHaveValue("typed-model");
});
