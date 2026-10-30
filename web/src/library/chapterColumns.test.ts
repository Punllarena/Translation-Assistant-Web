import { describe, expect, it } from "vitest";
import { COLUMNS, DEFAULT_COLUMNS, parseColumns, shownColumns, toggleColumn } from "./chapterColumns";

describe("chapterColumns", () => {
  it("defaults when nothing or garbage is saved", () => {
    expect(parseColumns(undefined)).toEqual(DEFAULT_COLUMNS);
    expect(parseColumns("images")).toEqual(DEFAULT_COLUMNS);
    expect(parseColumns({ images: true })).toEqual(DEFAULT_COLUMNS);
  });

  it("drops unknown ids, forces num and title, keeps display order", () => {
    expect(parseColumns(["images", "gone", "progress"])).toEqual(["num", "title", "progress", "images"]);
    expect(parseColumns([])).toEqual(["num", "title"]);
  });

  it("hides WordPress columns when WordPress is not set up", () => {
    expect(shownColumns(["num", "title", "wp", "wp_date"], false)).toEqual(["num", "title"]);
    expect(shownColumns(["num", "title", "wp", "wp_date"], true)).toEqual(["num", "title", "wp", "wp_date"]);
  });

  it("toggles a column and never hides num or title", () => {
    expect(toggleColumn(DEFAULT_COLUMNS, "images")).toEqual([...DEFAULT_COLUMNS, "images"]);
    expect(toggleColumn(DEFAULT_COLUMNS, "edited")).toEqual(["num", "title", "progress", "wp"]);
    expect(toggleColumn(DEFAULT_COLUMNS, "num")).toEqual(DEFAULT_COLUMNS);
    expect(toggleColumn(DEFAULT_COLUMNS, "title")).toEqual(DEFAULT_COLUMNS);
  });

  it("lists every column id once", () => {
    expect(new Set(COLUMNS.map((c) => c.id)).size).toBe(COLUMNS.length);
  });
});
