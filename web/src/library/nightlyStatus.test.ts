import { describe, expect, it } from "vitest";
import { newChapterBadges, nightlyNote } from "./nightlyStatus";

const base = { syosetu_url: "https://ncode.syosetu.com/n1/", status: "ongoing", archived_at: null, syosetu_nightly: true };

describe("nightlyNote", () => {
  it("is null for an eligible series", () => {
    expect(nightlyNote(base)).toBeNull();
  });
  it("is null with no syosetu URL (the section is hidden)", () => {
    expect(nightlyNote({ ...base, syosetu_url: "", syosetu_nightly: false })).toBeNull();
  });
  it("says why a series is skipped", () => {
    expect(nightlyNote({ ...base, status: "on_hold" })).toBe("Skipped: the series is not Ongoing.");
    expect(nightlyNote({ ...base, archived_at: "2026-01-01T00:00:00Z" })).toBe("Skipped: the series is archived.");
  });
  it("switched off wins over the other reasons", () => {
    expect(nightlyNote({ ...base, status: "dropped", archived_at: "2026-01-01T00:00:00Z", syosetu_nightly: false }))
      .toBe("Off for this series.");
  });
});

describe("newChapterBadges", () => {
  const doc = (id: number, series_id: number, series_order: number, translated_count: number) =>
    ({ id, series_id, series_order, line_count: 10, translated_count });
  it("counts the run's new chapters and links the first untranslated chapter", () => {
    const run = { series: [{ series_id: 1, new_chapters: 3 }, { series_id: 2, new_chapters: 0 }] };
    const docs = [doc(12, 1, 3, 0), doc(10, 1, 1, 10), doc(11, 1, 2, 4), doc(20, 2, 1, 0)];
    expect([...newChapterBadges(run, docs)]).toEqual([[1, { newChapters: 3, href: "/documents/11" }]]);
  });
  it("falls back to the series page when nothing is untranslated, and is empty with no run", () => {
    const run = { series: [{ series_id: 1, new_chapters: 2 }] };
    expect(newChapterBadges(run, [doc(10, 1, 1, 10)]).get(1)?.href).toBe("/series/1");
    expect(newChapterBadges(undefined, []).size).toBe(0);
  });
});
