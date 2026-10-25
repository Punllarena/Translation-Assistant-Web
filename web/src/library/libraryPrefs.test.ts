import { describe, expect, it } from "vitest";
import { DEFAULT_FILTERS, DEFAULT_SORT, type LibraryFilters } from "./libraryQuery";
import { readFilters, readSort, writeFilters, writeSort } from "./libraryPrefs";

const memory = () => {
  const m = new Map<string, string>();
  return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v), m };
};
const boom = () => { throw new Error("blocked"); };

describe("libraryPrefs", () => {
  it("round trips sort and filters under their keys", () => {
    const s = memory();
    writeSort({ key: "title", dir: "desc" }, s);
    const f: LibraryFilters = { sources: ["epub"], statuses: ["dropped", "completed"], wordpress: "none", archived: "only" };
    writeFilters(f, s);
    expect([...s.m.keys()]).toEqual(["ta.librarySort", "ta.libraryFilters"]);
    expect(readSort(s)).toEqual({ key: "title", dir: "desc" });
    expect(readFilters(s)).toEqual(f);
  });

  it("falls back on missing or bad JSON", () => {
    const empty = { getItem: () => null };
    expect(readSort(empty)).toEqual(DEFAULT_SORT);
    expect(readFilters(empty)).toEqual(DEFAULT_FILTERS);
    const bad = { getItem: () => "{nope" };
    expect(readSort(bad)).toEqual(DEFAULT_SORT);
    expect(readFilters(bad)).toEqual(DEFAULT_FILTERS);
    expect(readFilters({ getItem: () => "null" })).toEqual(DEFAULT_FILTERS);
  });

  it("falls back for an unknown sort key or direction", () => {
    expect(readSort({ getItem: () => '{"key":"nope","dir":"desc"}' })).toEqual(DEFAULT_SORT);
    expect(readSort({ getItem: () => '{"key":"title","dir":"sideways"}' })).toEqual(DEFAULT_SORT);
  });

  it("drops unknown values and fills missing groups", () => {
    expect(readFilters({ getItem: () => '{"statuses":["ongoing","paused"]}' })).toEqual({
      ...DEFAULT_FILTERS, statuses: ["ongoing"],
    });
    expect(readFilters({ getItem: () => '{"wordpress":"maybe","archived":7,"sources":"epub"}' })).toEqual(DEFAULT_FILTERS);
  });

  it("gives the defaults from a throwing storage", () => {
    expect(readSort({ getItem: boom })).toEqual(DEFAULT_SORT);
    expect(readFilters({ getItem: boom })).toEqual(DEFAULT_FILTERS);
    expect(() => writeSort(DEFAULT_SORT, { setItem: boom })).not.toThrow();
    expect(() => writeFilters(DEFAULT_FILTERS, { setItem: boom })).not.toThrow();
  });
});
