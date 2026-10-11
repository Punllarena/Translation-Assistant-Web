import { describe, expect, it } from "vitest";
import { groupDocuments, type Doc, type SeriesRow } from "./group";

const series = (id: number, title: string) => ({ id, title }) as SeriesRow;
const doc = (id: number, title: string, series_id: number | null, series_order = 0, updated_at = "2026-01-01T00:00:00Z") =>
  ({ id, title, chapter_title: "", series_id, series_order, updated_at }) as Doc;

const S = [series(2, "Volume 10"), series(1, "Volume 9")];
const D = [
  doc(1, "Ch 2", 1, 2),
  doc(2, "Ch 1", 1, 1),
  doc(3, "Loose old", null, 0, "2026-01-01T00:00:00Z"),
  doc(4, "Loose new", null, 0, "2026-02-01T00:00:00Z"),
  doc(5, "Ch 1", 2, 1),
];

describe("groupDocuments", () => {
  it("orders series naturally, chapters by series_order, unsorted last by recency", () => {
    const groups = groupDocuments(D, S, "");
    expect(groups.map((g) => g.series?.title ?? null)).toEqual(["Volume 9", "Volume 10", null]);
    expect(groups[0].docs.map((d) => d.id)).toEqual([2, 1]);
    expect(groups[2].docs.map((d) => d.id)).toEqual([4, 3]);
  });

  it("keeps empty series when not filtering", () => {
    expect(groupDocuments([], [series(1, "Empty")], "").map((g) => g.docs.length)).toEqual([0]);
  });

  it("filters case-insensitively on title and drops empty groups", () => {
    const groups = groupDocuments(D, S, "LOOSE");
    expect(groups).toHaveLength(1);
    expect(groups[0].docs.map((d) => d.id)).toEqual([4, 3]);
  });

  it("a series title match shows the whole series", () => {
    const groups = groupDocuments(D, S, "volume 10");
    expect(groups.map((g) => g.series?.id)).toEqual([2]);
    expect(groups[0].docs.map((d) => d.id)).toEqual([5]);
  });

  it("matches Japanese titles", () => {
    expect(groupDocuments([doc(9, "第一話", null)], [], "一話")[0].docs[0].id).toBe(9);
  });
});
