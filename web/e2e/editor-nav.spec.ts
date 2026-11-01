import { expect, test, type Page } from "@playwright/test";
import { openChapter } from "./fixtures/library";

async function open(page: Page, chapter: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
  await openChapter(page, "Nav series", chapter);
  await expect(page.getByRole("button", { name: "Next chapter", exact: true })).toBeVisible();
}

const card = (page: Page, index: number) => page.locator(`article[data-index="${index}"]`);

/** Reset the account's reading aid, whatever the page shows. */
async function readingsOff(page: Page) {
  await page.unroute("**/readings");
  await page.evaluate(() => fetch("/api/settings", {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reading_aid: "off" }),
  }));
}

test("chapter arrows and list", async ({ page }) => {
  await open(page, "Nav one");
  const oneUrl = page.url();
  await page.getByRole("button", { name: "Next chapter", exact: true }).click();
  await expect(page.getByText("二話目です。")).toBeVisible();
  expect(page.url()).not.toBe(oneUrl);
  const twoUrl = page.url();
  await page.getByRole("button", { name: "Previous chapter", exact: true }).click();
  await expect(page.getByText("今日は晴れ。")).toBeVisible();
  expect(page.url()).toBe(oneUrl);
  await page.getByRole("button", { name: /, chapter list$/ }).click();
  await page.getByRole("menuitemradio", { name: /^2 · Nav two/ }).click();
  await expect(page.getByText("二話目です。")).toBeVisible();
  expect(page.url()).toBe(twoUrl);
});

test("failed save stops the move", async ({ page }) => {
  await open(page, "Nav one");
  await page.route("**/documents/*/lines", (r) =>
    r.request().method() === "PATCH" ? r.fulfill({ status: 500 }) : r.continue());
  const oneUrl = page.url();
  await page.getByRole("textbox", { name: "Translation" }).click();
  await page.keyboard.type("Unsaved words.");
  await page.getByRole("button", { name: "Next chapter", exact: true }).click();
  await expect(page.getByText("Not moved: the last changes are not saved yet")).toBeVisible({ timeout: 10_000 });
  expect(page.url()).toBe(oneUrl);
});

test("author ruby always shows", async ({ page }) => {
  await open(page, "Nav one");
  await page.getByRole("button", { name: "Readings off" }).click();
  const big = card(page, 0).locator("ruby", { hasText: "大" });
  await expect(big.locator("rt")).toHaveText("おお");
  // the brackets are fallback text only: the drawn line never shows "(おお)"
  await expect(big.locator("rp")).toHaveCount(2);
  await expect(card(page, 0)).not.toContainText("(おお)", { useInnerText: true });
  await expect(card(page, 1).locator("ruby", { hasText: "STATUS" }).locator("rt")).toHaveText("ステータス");
});

test("reading aid on the active card", async ({ page }) => {
  await open(page, "Nav one");
  const status = await page.evaluate(async () => {
    const r = await fetch("/api/readings", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: "今日" }),
    });
    return r.ok ? await r.json() : null;
  });
  test.skip(!status || status.available === false, "MeCab is not installed");
  try {
    await card(page, 2).click();
    await page.getByRole("button", { name: "Hiragana readings" }).click();
    const today = card(page, 2).locator("ruby", { hasText: "今日" });
    await expect(today.locator("rt")).toHaveText("きょう");
    // a non-active card carries only its author ruby
    await expect(card(page, 3).locator("rt")).toHaveCount(0);
    await expect(card(page, 0).locator("rt")).toHaveCount(2);
    await page.getByRole("button", { name: "Romaji readings" }).click();
    await expect(card(page, 2).locator("ruby", { hasText: "今日" }).locator("rt")).toHaveText("kyō");
  } finally {
    await readingsOff(page);
  }
});

test("without MeCab the switch can still turn readings off", async ({ page }) => {
  await open(page, "Nav one");
  // the first answer comes at once; later ones wait, so the switch is seen between answers
  let release = () => {};
  const held = new Promise<void>((resolve) => { release = resolve; });
  let asked = 0;
  await page.route("**/readings", async (r) => {
    if (asked++ > 0) await held;
    // a held request the page gave up on (the line was left) is already gone
    await r.fulfill({ json: { available: false, message: "Readings need MeCab", tokens: [] } }).catch(() => {});
  });
  try {
    await page.getByRole("button", { name: "Hiragana readings" }).click();
    await expect(page.getByRole("button", { name: "Katakana readings" })).toBeDisabled();
    const off = page.getByRole("button", { name: "Readings off" });
    await expect(off).toBeEnabled();
    // moving to a line not asked about yet keeps the switch as it was
    await card(page, 2).click();
    await expect(page.getByRole("button", { name: "Katakana readings" })).toBeDisabled();
    await off.click();
    await expect(off).toHaveAttribute("aria-pressed", "true");
  } finally {
    release();
    await readingsOff(page);
  }
});

test("next untranslated on the active line brings it back", async ({ page }) => {
  await open(page, "Nav one");
  // line 1 is active and untranslated: the one button shown is "Next untranslated"
  await card(page, 22).scrollIntoViewIfNeeded();
  await expect(card(page, 0)).not.toBeInViewport();
  await expect(page.getByRole("button", { name: /^Back to editing/ })).toHaveCount(0);
  await page.getByRole("button", { name: "Next untranslated · line 1" }).click();
  await expect(card(page, 0)).toBeInViewport();
});

test("jump back", async ({ page }) => {
  await open(page, "Nav one");
  // line 1 translated and still active, so the next untranslated line is line 2 (a separate button)
  await card(page, 0).click();
  await card(page, 0).getByRole("textbox", { name: "Translation" }).click();
  await page.keyboard.type("One.");
  await card(page, 22).scrollIntoViewIfNeeded();
  await expect(page.getByRole("button", { name: "Back to editing · line 1" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Next untranslated · line 2" })).toBeVisible();
  await page.getByRole("button", { name: "Back to editing · line 1" }).click();
  await expect(card(page, 0)).toBeInViewport();
});

test("end card", async ({ page }) => {
  await open(page, "Nav two");
  await page.getByRole("textbox", { name: "Translation" }).click();
  await page.keyboard.type("The second story.");
  await expect(page.getByText("Saved", { exact: true })).toBeVisible({ timeout: 5_000 });
  await expect(page.getByText(/All 1 line translated/)).toBeVisible();
  await expect(page.getByText("Last chapter of the series")).toHaveCount(0);
  await expect(page.getByRole("link", { name: /^Next chapter →.*Nav blank$/ })).toBeVisible();
  await expect(page.getByRole("link", { name: "Back to series" })).toBeVisible();
});

test("a chapter with no lines keeps the way on", async ({ page }) => {
  await open(page, "Nav two");
  await page.getByRole("button", { name: "Next chapter", exact: true }).click();
  await expect(page.getByText("This chapter has no source text yet.")).toBeVisible();
  const crumbs = page.getByRole("navigation", { name: "Breadcrumb" });
  await expect(crumbs.getByRole("link", { name: "Nav series" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Next chapter", exact: true })).toBeDisabled();
  await expect(page.getByText("Last chapter of the series")).toBeVisible();
  await page.getByRole("button", { name: "Previous chapter", exact: true }).click();
  await expect(page.getByText("二話目です。")).toBeVisible();
  await page.getByRole("button", { name: "Next chapter", exact: true }).click();
  await expect(page.getByText("This chapter has no source text yet.")).toBeVisible();
});

/** Saves answer as told, so these flows leave the shared seed alone. */
async function fakeSaves(page: Page, status: () => number) {
  await page.route("**/documents/*/lines", (r) => r.request().method() === "PATCH"
    ? r.fulfill({ status: status(), contentType: "application/json", body: status() === 200 ? '{"missing":[]}' : "" })
    : r.continue());
}
const box = (page: Page) => page.getByRole("textbox", { name: "Translation" });

test("focus comes home: toggles, the card's own source, Esc and stray typing", async ({ page }) => {
  await open(page, "Nav one");
  await fakeSaves(page, () => 200);
  await box(page).click();
  await page.getByRole("button", { name: "Translation memory", exact: true }).click();
  await page.keyboard.type("a");
  await expect(box(page)).toHaveText("One.a");
  await page.getByRole("button", { name: "Translation memory", exact: true }).click();
  await card(page, 0).locator("p.source").click();
  await page.keyboard.type("b");
  await expect(box(page)).toHaveText("One.ab");
  await page.getByRole("button", { name: "Next chapter", exact: true }).focus();
  await page.keyboard.press("Escape");
  await expect(box(page)).toBeFocused();
  await page.evaluate(() => (document.activeElement as HTMLElement).blur());
  await page.keyboard.type("c");
  await expect(box(page)).toHaveText("One.abc");
  await page.getByRole("button", { name: "Machine translation", exact: true }).focus();
  await page.keyboard.press("Control+ArrowDown");
  await expect(card(page, 1)).toHaveAttribute("aria-current", "true");
});

test("a failing save retries itself, names its lines, and guards header links", async ({ page }) => {
  await open(page, "Nav one");
  let status = 500;
  await fakeSaves(page, () => status);
  const url = page.url();
  await box(page).click();
  await page.keyboard.type("Words.");
  await expect(page.getByRole("alert")).toContainText("not saved: The server answered 500. Retrying…", { timeout: 10_000 });
  await page.getByRole("link", { name: "Statistics" }).click();
  const dialog = page.getByRole("dialog", { name: "Leave with unsaved lines?" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Cancel" }).click();
  expect(page.url()).toBe(url);
  status = 200;
  await expect(page.locator(".save-state")).toHaveText("Saved", { timeout: 40_000 });
  await page.getByRole("link", { name: "Statistics" }).click();
  await expect(page).toHaveURL(/stat/);
});

/** One translation-memory answer, or a slow one for every line but the first. */
async function tmAnswers(page: Page, slowMs = 0) {
  await page.route("**/tm/matches*", async (r) => {
    const line = new URL(r.request().url()).searchParams.get("line_number");
    if (line !== "0" && slowMs) await new Promise((done) => setTimeout(done, slowMs));
    const text = line === "0" ? "Old match" : "New match";
    await r.fulfill({ json: [{ translated_text: text, document_title: "Other", updated_at: "2026-01-01T00:00:00Z" }] }).catch(() => {});
  });
}

/** The backends the machine-translation test turns on, put back whatever the page set. */
async function mtBackends(page: Page, enabled: string[]) {
  const put = await page.request.put("/api/settings", { data: { mt_enabled: enabled } });
  if (!put.ok()) throw new Error(`the backends could not be set: ${put.status()}`);
}

test("Use can't take a stale or partial suggestion", async ({ page }) => {
  await tmAnswers(page, 1000);
  await page.route("**/mt/stream*", (r) => {
    const line = new URL(r.request().url()).searchParams.get("line_number");
    // a stream that sends a chunk and then ends without done is still running
    const body = line === "0"
      ? 'event: chunk\ndata: {"text":"partial"}\n\n'
      : 'event: result\ndata: {"text":"Partial"}\n\nevent: done\ndata: {}\n\n';
    return r.fulfill({ status: 200, headers: { "Content-Type": "text/event-stream" }, body });
  });
  await open(page, "Nav one");
  await fakeSaves(page, () => 200);
  await mtBackends(page, ["mecab", "jparser", "deepl"]);
  try {
    await page.reload();
    await expect(page.getByRole("complementary", { name: "Translation memory" })).toContainText("Old match");
    await box(page).click();
    await page.keyboard.type("draft");
    // a card still streaming offers no Use
    const deepl = page.getByRole("region", { name: "DeepL" });
    await expect(deepl).toContainText("partial");
    await expect(deepl.locator("[data-use]")).toHaveCount(0);
    // line 2's memory still holds line 1's match while its own answer is on the way
    await page.keyboard.press("Enter");
    await expect(card(page, 1)).toHaveAttribute("aria-current", "true");
    await page.keyboard.press("Alt+1");
    await expect(box(page)).not.toContainText("Old match");
    await page.keyboard.press("PageDown");
    await expect(page.getByRole("region", { name: "DeepL" })).toContainText("Partial");
    await expect(page.getByRole("region", { name: "DeepL" }).locator("[data-use]")).toHaveCount(1);
  } finally {
    await mtBackends(page, ["mecab", "jparser"]);
  }
});

test("suggestion numbers don't move", async ({ page }) => {
  await tmAnswers(page, 1000);
  await page.route("**/mt/stream*", (r) => r.fulfill({ status: 200, headers: { "Content-Type": "text/event-stream" },
    body: 'event: result\ndata: {"text":"Machine"}\n\nevent: done\ndata: {}\n\n' }));
  await open(page, "Nav one");
  await fakeSaves(page, () => 200);
  await mtBackends(page, ["mecab", "jparser", "deepl"]);
  try {
    await page.reload();
    const use = page.getByRole("region", { name: "DeepL" }).locator("[data-use]");
    await expect(use).toHaveAttribute("data-use", "3");
    const panel = page.getByRole("complementary", { name: "Translation memory" });
    await expect(panel).toContainText("Old match");
    await expect(use).toHaveAttribute("data-use", "3");
    await expect(panel.locator('[data-use="1"]')).toHaveText(/Old match/);
  } finally {
    await mtBackends(page, ["mecab", "jparser"]);
  }
});

test("undo survives moving between lines, per chapter", async ({ page }) => {
  const patches: { lines: { line_number: number; translated_text: string }[] }[] = [];
  await page.route("**/documents/*/lines", (r) => {
    if (r.request().method() !== "PATCH") return r.continue();
    patches.push(r.request().postDataJSON());
    return r.fulfill({ json: { missing: [] } });
  });
  await page.route("**/tm/matches*", (r) => r.fulfill({ json: [{ translated_text: "From memory",
    document_title: "Other", updated_at: "2026-01-01T00:00:00Z" }] }));
  await open(page, "Nav one");
  await box(page).click();
  const original = (await box(page).textContent()) ?? ""; // an earlier test may have typed here
  await page.keyboard.press("Alt+1");
  await expect(box(page)).toHaveText("From memory");
  await page.keyboard.press("Enter");
  await expect(card(page, 1)).toHaveAttribute("aria-current", "true");
  await page.keyboard.press("PageUp");
  await expect(card(page, 0)).toHaveAttribute("aria-current", "true");
  await page.keyboard.press("Control+z");
  await expect(box(page)).toHaveText(original);
  await expect.poll(() => patches.some((p) => p.lines.some(
    (l) => l.line_number === 0 && l.translated_text === original))).toBe(true);
  // another chapter's first line has its own history, so the same line number does not undo there
  await page.getByRole("button", { name: /, chapter list$/ }).click();
  await page.getByRole("menuitemradio", { name: /^2 · Nav two/ }).click();
  const other = (await box(page).textContent()) ?? "";
  await page.keyboard.press("Control+z");
  await expect(box(page)).toHaveText(other);
  await expect(box(page)).not.toHaveText("From memory");
});

test("replacing says so", async ({ page }) => {
  await page.route("**/tm/matches*", (r) => r.fulfill({ json: [{ translated_text: "From memory",
    document_title: "Other", updated_at: "2026-01-01T00:00:00Z" }] }));
  await open(page, "Nav one");
  await fakeSaves(page, () => 200);
  // line 3: no other flow in this file types into it, so it starts empty
  await card(page, 2).click();
  await box(page).click();
  await page.keyboard.press("Alt+1"); // an empty line: nothing was replaced
  await expect(box(page)).toHaveText("From memory");
  await expect(page.getByText(/^Replaced line 3\./)).toHaveCount(0);
  await page.keyboard.type("draft");
  await page.keyboard.press("Alt+1");
  await expect(page.getByText("Replaced line 3. Ctrl+Z brings it back")).toBeVisible();
});

test("a permanent error stops retrying and offers the text", async ({ context, page }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await open(page, "Nav one");
  let patches = 0;
  await page.route("**/documents/*/lines", (r) => {
    if (r.request().method() !== "PATCH") return r.continue();
    patches++;
    return r.fulfill({ status: 422, contentType: "application/json", body: '{"detail":[{"loc":["body","lines",0],"msg":"bad"}]}' });
  });
  const title = await page.locator(".ch-title").boundingBox();
  await box(page).click();
  await page.keyboard.type("Words.");
  const alert = page.getByRole("alert");
  await expect(alert).toContainText("Line 1 not saved: The server refused this text. It may be too long.");
  await expect(alert).not.toContainText("Retrying");
  await page.waitForTimeout(6000);
  expect(patches).toBe(1);
  // the alert has a row of its own: the chapter title keeps its width
  expect((await page.locator(".ch-title").boundingBox())!.width).toBeCloseTo(title!.width, 0);
  const text = await box(page).textContent();
  await page.getByRole("button", { name: "Copy unsaved text" }).click();
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  // Windows hands clipboard lines back with CRLF, whatever was written
  expect(copied.replace(/\r\n/g, "\n")).toBe(`Line 1\n${text}`);
});

test("the alert stays through retries and typing", async ({ page }) => {
  await open(page, "Nav one");
  let release = () => {};
  const held = new Promise<void>((done) => { release = done; });
  let patches = 0;
  await page.route("**/documents/*/lines", async (r) => {
    if (r.request().method() !== "PATCH") return r.continue();
    if (patches++ === 0) return r.fulfill({ status: 500 });
    await held;
    await r.fulfill({ status: 500 }).catch(() => {});
  });
  await box(page).click();
  await page.keyboard.type("W");
  const alert = page.getByRole("alert");
  const retry = page.getByRole("button", { name: "Retry" });
  await expect(alert).toContainText("not saved: The server answered 500.");
  await expect.poll(() => patches).toBeGreaterThanOrEqual(2); // the retry is in flight
  await expect(alert).toContainText("The server answered 500.");
  await expect(retry).toBeVisible();
  release();
  await page.keyboard.type("x");
  await expect(alert).toContainText("The server answered 500.");
  await expect(retry).toBeVisible();
});

test("missing lines are a failure", async ({ context, page }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await open(page, "Nav one");
  await page.route("**/documents/*/lines", (r) => r.request().method() === "PATCH"
    ? r.fulfill({ status: 200, contentType: "application/json", body: '{"missing":[0]}' })
    : r.continue());
  await box(page).click();
  await page.keyboard.type("Words.");
  await expect(page.locator(".save-state")).toHaveText("Not saved");
  await expect(page.getByRole("alert")).toContainText("Line 1 no longer exists; reload the chapter");
  const text = await box(page).textContent();
  await page.getByRole("button", { name: "Copy unsaved text" }).click();
  expect((await page.evaluate(() => navigator.clipboard.readText())).replace(/\r\n/g, "\n")).toBe(`Line 1\n${text}`);
});

test("notices expire", async ({ page }) => {
  await open(page, "Nav one");
  await fakeSaves(page, () => 200);
  await box(page).click();
  await page.keyboard.press("Alt+9");
  const notice = page.getByText("No suggestion 9 on this line");
  await expect(notice).toBeVisible();
  await expect(notice).toHaveCount(0, { timeout: 10_000 });
  await page.keyboard.press("Alt+9");
  await expect(notice).toBeVisible();
  await page.keyboard.press("PageDown");
  await expect(notice).toHaveCount(0);
});

test("unsaved cards are marked", async ({ page }) => {
  await open(page, "Nav one");
  await fakeSaves(page, () => 500);
  await box(page).click();
  await page.keyboard.type("Words.");
  const dot = page.locator("article.card.active .unsaved-dot");
  await expect(dot).toHaveAttribute("aria-label", "Not saved");
  await expect(dot).toHaveAttribute("title", "Not saved");
});

test("the keyboard reaches the aids; the find bar leaves the save state visible", async ({ page }) => {
  await page.route("**/tm/matches*", (r) => r.fulfill({ contentType: "application/json",
    body: JSON.stringify([{ translated_text: "From memory", document_title: "Other", updated_at: "2026-01-01T00:00:00Z" }]) }));
  await open(page, "Nav one");
  await fakeSaves(page, () => 200);
  await box(page).click();
  await page.keyboard.press("Alt+1");
  await expect(box(page)).toHaveText("From memory");
  await page.keyboard.press("Alt+9");
  await expect(page.getByText("No suggestion 9 on this line")).toBeVisible();
  await page.keyboard.press("Control+/");
  const help = page.getByRole("dialog", { name: "Keyboard shortcuts" });
  await expect(help.getByText("Use suggestion 1")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(box(page)).toBeFocused();
  await page.keyboard.press("Control+f");
  await page.mouse.wheel(0, 600);
  const save = await page.locator(".save-state").boundingBox();
  const bar = await page.locator(".findbar").boundingBox();
  expect(save!.y + save!.height).toBeLessThanOrEqual(bar!.y);
  await page.keyboard.press("Escape");
  await page.keyboard.press("Alt+PageDown");
  await expect(page.getByText("二話目です。")).toBeVisible();
});
