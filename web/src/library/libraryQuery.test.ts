import { describe, expect, it } from "vitest";
import {
  DEFAULT_FILTERS, activeGroups, emptyReason, filterCards, sortCards,
  type LibraryFilters, type SortKey,
} from "./libraryQuery";
import type { SeriesCard, SeriesRow } from "./shelf";

interface Over extends Partial<Omit<SeriesCard, "series">> {
  title?: string;
  status?: SeriesRow["status"];
  source?: SeriesRow["source"];
  archived_at?: string | null;
  syosetu_updated_at?: string | null;
}

let n = 0;
const card = (o: Over = {}): SeriesCard => {
  const { title = `S${++n}`, status = "ongoing", source = "other", archived_at = null, syosetu_updated_at = null, ...rest } = o;
  return {
    series: { id: ++n, title, status, source, archived_at, syosetu_updated_at } as SeriesRow,
    coverImageId: null, volumeCount: 0, chapterCount: 0, progress: 0,
    editedAt: null, addedAt: null, publishedAt: null, hasPublished: false,
    ...rest,
  };
};
const titles = (cs: SeriesCard[]) => cs.map((c) => c.series.title);
const F = (o: Partial<LibraryFilters>): LibraryFilters => ({ ...DEFAULT_FILTERS, ...o });

describe("filterCards", () => {
  it("combines groups with AND and ticks with OR", () => {
    const cs = [
      card({ title: "a", source: "syosetu", status: "ongoing" }),
      card({ title: "b", source: "epub", status: "ongoing" }),
      card({ title: "c", source: "syosetu", status: "dropped" }),
    ];
    const f = F({ sources: ["syosetu"], statuses: ["ongoing", "dropped"] });
    expect(titles(filterCards(cs, f, ""))).toEqual(["a", "c"]);
  });

  it("hides archived by default; include and only", () => {
    const cs = [card({ title: "old", archived_at: "2026-01-01T00:00:00Z" }), card({ title: "new" })];
    expect(titles(filterCards(cs, DEFAULT_FILTERS, ""))).toEqual(["new"]);
    expect(titles(filterCards(cs, F({ archived: "include" }), ""))).toEqual(["old", "new"]);
    expect(titles(filterCards(cs, F({ archived: "only" }), ""))).toEqual(["old"]);
  });

  it("filters by wordpress published / none", () => {
    const cs = [card({ title: "p", hasPublished: true }), card({ title: "q" })];
    expect(titles(filterCards(cs, F({ wordpress: "published" }), ""))).toEqual(["p"]);
    expect(titles(filterCards(cs, F({ wordpress: "none" }), ""))).toEqual(["q"]);
    expect(titles(filterCards(cs, F({ wordpress: "any" }), ""))).toEqual(["p", "q"]);
  });

  it("ANDs the search with the filters", () => {
    const cs = [
      card({ title: "Alpha Tale", status: "ongoing" }),
      card({ title: "Alpha Two", status: "dropped" }),
      card({ title: "Beta", status: "ongoing" }),
    ];
    expect(titles(filterCards(cs, F({ statuses: ["ongoing"] }), " ALPHA "))).toEqual(["Alpha Tale"]);
  });
});

describe("sortCards", () => {
  const d = (day: number) => `2026-01-0${day}T00:00:00Z`;
  const cs = [
    card({ title: "b", editedAt: d(2), syosetu_updated_at: d(3), addedAt: d(1), progress: 50, publishedAt: d(2), chapterCount: 5 }),
    card({ title: "a", editedAt: d(3), syosetu_updated_at: d(1), addedAt: d(3), progress: 10, publishedAt: d(1), chapterCount: 9 }),
    card({ title: "c", editedAt: d(1), syosetu_updated_at: d(2), addedAt: d(2), progress: 90, publishedAt: d(3), chapterCount: 1 }),
  ];
  const expected: Record<SortKey, string[]> = {
    modified: ["a", "b", "c"],
    syosetu: ["b", "c", "a"],
    added: ["a", "c", "b"],
    title: ["a", "b", "c"],
    progress: ["c", "b", "a"],
    published: ["c", "b", "a"],
    chapters: ["a", "b", "c"],
  };
  it.each(Object.keys(expected) as SortKey[])("sorts by %s in its default direction", (key) => {
    const dir = key === "title" ? "asc" : "desc";
    expect(titles(sortCards(cs, { key, dir }))).toEqual(expected[key]);
  });

  it("reverses with the direction and does not mutate", () => {
    const before = titles(cs);
    expect(titles(sortCards(cs, { key: "chapters", dir: "asc" }))).toEqual(["c", "b", "a"]);
    expect(titles(cs)).toEqual(before);
  });

  it("breaks ties by title", () => {
    const tied = [card({ title: "z", progress: 5 }), card({ title: "m", progress: 5 })];
    expect(titles(sortCards(tied, { key: "progress", dir: "desc" }))).toEqual(["m", "z"]);
    expect(titles(sortCards(tied, { key: "progress", dir: "asc" }))).toEqual(["m", "z"]);
  });

  it("keeps missing values last in both directions", () => {
    const m = [
      card({ title: "none", syosetu_updated_at: null, publishedAt: null }),
      card({ title: "old", syosetu_updated_at: d(1), publishedAt: d(1) }),
      card({ title: "new", syosetu_updated_at: d(2), publishedAt: d(2) }),
    ];
    for (const key of ["syosetu", "published"] as const) {
      expect(titles(sortCards(m, { key, dir: "desc" }))).toEqual(["new", "old", "none"]);
      expect(titles(sortCards(m, { key, dir: "asc" }))).toEqual(["old", "new", "none"]);
    }
  });
});

describe("activeGroups", () => {
  it("counts groups off default", () => {
    expect(activeGroups(DEFAULT_FILTERS)).toBe(0);
    expect(activeGroups(F({ sources: ["epub"] }))).toBe(1);
    expect(activeGroups(F({ sources: ["epub"], statuses: ["dropped"], wordpress: "none", archived: "only" }))).toBe(4);
  });
});

describe("emptyReason", () => {
  const old = "2026-01-01T00:00:00Z";
  it("distinguishes no series, all archived and no match", () => {
    expect(emptyReason([], DEFAULT_FILTERS, "")).toBe("none");
    const archived = [card({ archived_at: old }), card({ archived_at: old })];
    expect(emptyReason(archived, DEFAULT_FILTERS, "")).toBe("all-archived");
    expect(emptyReason(archived, F({ archived: "include" }), "zzz")).toBe("no-match");
    expect(emptyReason([card(), card({ archived_at: old })], DEFAULT_FILTERS, "zzz")).toBe("search");
    expect(emptyReason([card()], DEFAULT_FILTERS, "  ")).toBe("no-match");
    expect(emptyReason([card()], F({ statuses: ["dropped"] }), "zzz")).toBe("no-match");
  });
});
