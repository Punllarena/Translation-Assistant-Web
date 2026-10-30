import { describe, expect, it } from "vitest";
import { COLUMNS, DEFAULT_COLUMNS, parseColumns, shownColumns, toggleColumn, columnWidth, tableMinWidthRem } from "./chapterColumns";

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

describe("column widths", () => {
  it("gives every column but the title a fixed width", () => {
    for (const c of COLUMNS) expect(columnWidth(c.id) === undefined).toBe(c.id === "title");
  });

  it("the table is at least the fixed columns plus room for the title", () => {
    // grip 2.25 + check 2 + menu 3.5 + title 10 + num 3 + progress 6.25 + edited 6 + wp 6.5
    expect(tableMinWidthRem(DEFAULT_COLUMNS, { grip: true, narrow: false })).toBe(39.5);
    expect(tableMinWidthRem(DEFAULT_COLUMNS, { grip: false, narrow: false })).toBe(37.25);
  });

  it("phone widths leave out the columns the narrow layout hides", () => {
    // check 2 + menu 3.5 + title 10 + num 3 + images 4.25
    expect(tableMinWidthRem([...DEFAULT_COLUMNS, "images"], { grip: true, narrow: true })).toBe(22.75);
  });
});
