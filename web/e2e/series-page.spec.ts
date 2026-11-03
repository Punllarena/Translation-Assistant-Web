import { expect, test, type Page } from "@playwright/test";
import { openSeries } from "./fixtures/library";

// These tests run in order: the last one deletes a seeded chapter, so the earlier ones go first.

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
}

const SERIES = "Series page spec";
const row = (page: Page, text: string) => page.getByRole("row").filter({ hasText: text });
const overflow = (page: Page) =>
  page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);

/** The selection bar's "Publish selected…" needs a WordPress credential. publish.spec normally
 *  saves one first, but this spec must also pass on its own, so it creates one when missing. */
async function ensureWordPress(page: Page) {
  const list = (await (await page.request.get("/api/credentials")).json()) as
    { kind: string; name: string; endpoint_url: string }[];
  if (list.some((c) => c.kind === "wordpress" && c.name === "" && c.endpoint_url !== "")) return;
  const created = await page.request.post("/api/credentials", {
    data: { kind: "wordpress", name: "", secret: "e2e-plugin-key", endpoint_url: "http://127.0.0.1:9" },
  });
  expect(created.ok()).toBe(true);
}

test.describe.configure({ mode: "serial" });

test("a row click in select mode ticks it and never opens the editor", async ({ page }) => {
  await signIn(page);
  await openSeries(page, SERIES);
  await page.getByLabel("Select Spec one").check();
  await expect(page.getByText("1 selected")).toBeVisible();
  const before = page.url();
  await row(page, "Spec image").locator(".ch-title").click();
  await expect(page.getByText("2 selected")).toBeVisible();
  expect(page.url()).toBe(before);
  await expect(page.getByRole("button", { name: "Clear" })).toBeVisible();
  await page.getByRole("button", { name: "Clear" }).click();
  await expect(page.getByText("2 selected")).toHaveCount(0);
});

test("shift-click ticks the range of shown rows", async ({ page }) => {
  await signIn(page);
  await openSeries(page, SERIES);
  await page.getByLabel("Select Spec one").check();
  await row(page, "Spec image").locator(".ch-title").click({ modifiers: ["Shift"] });
  await expect(page.getByText("3 selected")).toBeVisible();
});

test("a 200-character title does not push the page sideways", async ({ page }) => {
  await signIn(page);
  await openSeries(page, SERIES);
  for (const [width, height] of [[1280, 800], [375, 812]] as const) {
    await page.setViewportSize({ width, height });
    expect(await overflow(page), `${width}×${height}`).toBeLessThanOrEqual(0);
  }
});

test("Columns shows a column, and the choice survives a reload", async ({ page }) => {
  await signIn(page);
  await openSeries(page, SERIES);
  const imagesHeader = page.getByRole("columnheader", { name: "Images" });
  await expect(imagesHeader).toHaveCount(0);
  await page.getByRole("button", { name: "Columns ▾" }).click();
  await page.getByRole("menuitemcheckbox", { name: "Images" }).click();
  await expect(imagesHeader).toBeVisible();
  await page.keyboard.press("Escape");
  await page.reload();
  await expect(page.getByRole("columnheader", { name: "Images" })).toBeVisible();
  // back to the defaults, so the rest of the suite sees the usual columns
  await page.getByRole("button", { name: "Columns ▾" }).click();
  await page.getByRole("menuitemcheckbox", { name: "Images" }).click();
  await expect(page.getByRole("columnheader", { name: "Images" })).toHaveCount(0);
});

test("every menu stays inside a phone viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signIn(page);
  await openSeries(page, SERIES);
  for (const name of ["Columns ▾", "Volume actions", "Export volume ▾"]) {
    await page.getByRole("button", { name, exact: true }).click();
    const rect = await page.getByRole("menu").evaluate((el) => {
      const r = el.getBoundingClientRect();
      return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, w: window.innerWidth, h: window.innerHeight };
    });
    expect(rect.left, name).toBeGreaterThanOrEqual(0);
    expect(rect.right, name).toBeLessThanOrEqual(rect.w);
    expect(rect.top, name).toBeGreaterThanOrEqual(0);
    expect(rect.bottom, name).toBeLessThanOrEqual(rect.h);
    expect(await overflow(page), name).toBeLessThanOrEqual(0);
    await page.keyboard.press("Escape");
  }
});

test("arrow keys skip a disabled menu item", async ({ page }) => {
  await signIn(page);
  await openSeries(page, SERIES);
  // The first row cannot move up, so its menu holds a disabled "Move up".
  await page.locator(".chapters tbody tr").first().getByRole("button", { name: /^Actions for/ }).click();
  await expect(page.getByRole("menuitem", { name: "Open" })).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("menuitem", { name: "Rename…" })).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("menuitem", { name: "Move down" })).toBeFocused();
});

test("a disabled quiet button is lighter than an enabled one", async ({ page }) => {
  await signIn(page);
  await openSeries(page, SERIES);
  const opacity = await page.evaluate(() => {
    const make = (disabled: boolean) => {
      const b = document.createElement("button");
      b.className = "quiet small";
      b.disabled = disabled;
      document.body.append(b);
      const o = getComputedStyle(b).opacity;
      b.remove();
      return Number(o);
    };
    return { on: make(false), off: make(true) };
  });
  expect(opacity.off).toBeLessThan(opacity.on);
});

test("scrolling inside a tall row menu does not close it", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 500 });
  await signIn(page);
  await openSeries(page, SERIES);
  await page.getByRole("button", { name: "Actions for Spec one" }).click();
  const menu = page.locator(".menu-fixed");
  await expect(menu).toBeVisible();
  expect(await menu.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true);
  await menu.evaluate((el) => { el.scrollTop = 80; });
  await page.waitForTimeout(150); // a scroll event is async; give a wrongly attached listener time to close it
  await expect(menu).toBeVisible();
});

test("a row's ⋯ menu is not clipped by the table wrapper", async ({ page }) => {
  // Tall enough that the whole menu has room: the point is that the wrapper does not clip it.
  await page.setViewportSize({ width: 1280, height: 1300 });
  await signIn(page);
  await openSeries(page, SERIES);
  await page.getByRole("button", { name: "Actions for Spec one" }).click();
  const items = page.locator(".menu [role=menuitem]");
  await expect(items.first()).toBeVisible();
  const boxes = await items.evaluateAll((els) => els.map((el) => {
    const r = el.getBoundingClientRect();
    const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return {
      top: r.top, left: r.left, right: r.right, bottom: r.bottom,
      viewport: { w: window.innerWidth, h: window.innerHeight },
      hit: hit !== null && (hit === el || el.contains(hit)),
    };
  }));
  expect(boxes.length).toBeGreaterThan(10);
  for (const b of boxes) {
    expect(b.top).toBeGreaterThanOrEqual(0);
    expect(b.left).toBeGreaterThanOrEqual(0);
    expect(b.right).toBeLessThanOrEqual(b.viewport.w);
    expect(b.bottom).toBeLessThanOrEqual(b.viewport.h);
    expect(b.hit).toBe(true);
  }
  const wrap = await page.locator(".chapters-wrap")
    .evaluate((el) => ({ scroll: el.scrollHeight, client: el.clientHeight }));
  expect(wrap.scroll).toBeLessThanOrEqual(wrap.client + 1);
});

test("the chapter menu groups its items and keeps Delete last", async ({ page }) => {
  await signIn(page);
  await openSeries(page, SERIES);
  await page.getByRole("button", { name: "Actions for Spec one" }).click();
  const menu = page.locator(".menu");
  const items = await menu.getByRole("menuitem").allTextContents();
  expect(items.at(-1)).toBe("Delete");
  const group = (label: string) =>
    menu.getByRole("group", { name: label }).getByRole("menuitem").allTextContents();
  expect(await group("Chapter")).toEqual(["Open", "Rename…"]);
  expect(await group("Reorder")).toEqual(["Move up", "Move down"]);
  expect(await group("Export")).toEqual(["Export TXT", "Export Markdown", "Export Ruby Markdown"]);
  const pipeline = await group("Pipeline");
  expect(pipeline.indexOf("Queue for Ollama")).toBeGreaterThanOrEqual(0);
  expect(pipeline.indexOf("Flush Ollama output…")).toBeGreaterThan(pipeline.indexOf("Queue for Ollama"));
  expect(await menu.locator(":scope > [role=separator]").count()).toBeGreaterThanOrEqual(3);
  await page.keyboard.press("Escape");
});

test("Select mode with nothing ticked shows quick picks but no selection bar", async ({ page }) => {
  await signIn(page);
  await openSeries(page, SERIES);
  const chapters = await page.locator(".chapters tbody tr").count();
  const tools = page.locator(".ch-tools");
  await tools.getByRole("button", { name: "Select", exact: true }).click();
  await expect(page.getByRole("toolbar", { name: "Selected chapters" })).toHaveCount(0);
  await tools.getByRole("button", { name: "Pick ▾" }).click();
  await page.getByRole("menuitem", { name: "All", exact: true }).click();
  await expect(page.getByRole("toolbar", { name: "Selected chapters" })).toBeVisible();
  await expect(page.getByText(`${chapters} selected`)).toBeVisible();
});

test("ticking the first row in Select mode does not move the rows", async ({ page }) => {
  await signIn(page);
  await openSeries(page, SERIES);
  await page.locator(".ch-tools").getByRole("button", { name: "Select", exact: true }).click();
  const second = page.locator(".chapters tbody tr").nth(1);
  const before = (await second.boundingBox())!.y;
  await page.locator(".chapters tbody tr").first().locator(".ch-title").click();
  await expect(page.getByRole("toolbar", { name: "Selected chapters" })).toBeVisible();
  expect(Math.abs((await second.boundingBox())!.y - before)).toBeLessThan(2);
  await page.getByRole("button", { name: "Clear" }).click();
});

test("with rows ticked, Publish volume is not a second solid primary", async ({ page }) => {
  await signIn(page);
  await ensureWordPress(page);
  await openSeries(page, SERIES);
  const publishVolume = page.getByRole("button", { name: "Publish volume…" });
  await page.getByLabel("Select Spec one").check();
  const publishSelected = page.getByRole("button", { name: "Publish selected…" });
  await expect(publishSelected).toBeVisible();
  const colour = (locator: typeof publishVolume) =>
    locator.evaluate((el) => getComputedStyle(el).backgroundColor);
  expect(await colour(publishVolume)).not.toBe(await colour(publishSelected));
  await page.getByRole("button", { name: "Clear" }).click();
});

test("at 390px wide, ticking the first row does not move the rows", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signIn(page);
  await ensureWordPress(page); // the full bar (with its WordPress buttons) is what used to wrap
  await openSeries(page, SERIES);
  await page.locator(".ch-tools").getByRole("button", { name: "Select", exact: true }).click();
  const second = page.locator(".chapters tbody tr").nth(1);
  const before = (await second.boundingBox())!.y;
  await page.locator(".chapters tbody tr").first().locator(".ch-title").click();
  await expect(page.getByRole("toolbar", { name: "Selected chapters" })).toBeVisible();
  expect(Math.abs((await second.boundingBox())!.y - before)).toBeLessThan(2);
});

test("the Volumes tab has no series-wide Ollama buttons, and the Tools tab has them", async ({ page }) => {
  await signIn(page);
  await openSeries(page, SERIES);
  await expect(page.getByRole("button", { name: "Queue series for Ollama" })).toHaveCount(0);
  await page.getByRole("tab", { name: "Tools" }).click();
  await expect(page.getByRole("button", { name: "Queue series for Ollama" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Flush Ollama output…" })).toBeVisible();
});

test("the selection bar's More menu offers Move to and Merge…, and Merge needs two rows", async ({ page }) => {
  await signIn(page);
  await openSeries(page, SERIES);
  await page.getByLabel("Select Spec one").check();
  await expect(page.getByRole("button", { name: "Move to…" })).toHaveCount(0);
  const more = page.getByRole("button", { name: "More ▾" });
  await more.click();
  await expect(page.getByRole("menuitem", { name: "Merge…" })).toBeDisabled();
  await page.getByLabel("Select Spec image").check();
  await more.click();
  await expect(page.getByRole("menuitem", { name: "Merge…" })).toBeEnabled();
  await page.keyboard.press("Escape");
  await expect(more).toBeFocused();
});

test("series tabs read Volumes, Glossary, Gallery, Tools, Settings in that order", async ({ page }) => {
  await signIn(page);
  await openSeries(page, SERIES);
  await expect(page.getByRole("tab")).toHaveText(["Volumes", "Glossary", "Gallery", "Tools", "Settings"]);
});

test("Move down in a chapter's menu reorders it and survives a reload", async ({ page }) => {
  await signIn(page);
  await openSeries(page, SERIES);
  const long = "長".repeat(200);
  const titles = () => page.locator(".chapters tbody .ch-title");
  await expect(titles()).toHaveText(["Spec one", long, "Spec image"]);
  await page.getByRole("button", { name: "Actions for Spec one" }).click();
  await page.getByRole("menuitem", { name: "Move down" }).click();
  await expect(titles()).toHaveText([long, "Spec one", "Spec image"]);
  await page.reload();
  await expect(titles()).toHaveText([long, "Spec one", "Spec image"]);
  // A syosetu series keeps syosetu's numbering, so its rows offer no Move up / Move down.
  await openSeries(page, "Filter spec ongoing");
  await page.getByRole("button", { name: /^Actions for / }).click();
  await expect(page.getByRole("menuitem", { name: "Move up" })).toHaveCount(0);
});

test("deleting a chapter with an image offers to move it, and the Illustrations chapter appears", async ({ page }) => {
  await signIn(page);
  await openSeries(page, SERIES);
  await page.getByLabel("Select Spec image").check();
  await page.getByRole("button", { name: "Delete", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("Move their images to the volume's Illustrations chapter")).toBeVisible();
  await dialog.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("link", { name: "Open Illustrations" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Open Spec image" })).toHaveCount(0);
});
