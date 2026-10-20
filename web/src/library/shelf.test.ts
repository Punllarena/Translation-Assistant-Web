import { describe, expect, it } from "vitest";
import { seriesCards, sizeLabel, type Doc, type SeriesRow, type Volume } from "./shelf";

const series = (id: number, title: string) => ({ id, title }) as SeriesRow;
const volume = (id: number, series_id: number, volume_order: number) => ({ id, series_id, volume_order }) as Volume;
const doc = (id: number, series_id: number, volume_id: number | null, o: Partial<Doc> = {}) =>
  ({ id, series_id, volume_id, series_order: id, line_count: 0, translated_count: 0, updated_at: "2026-01-01T00:00:00Z", ...o }) as Doc;

describe("seriesCards", () => {
  it("handles an empty series", () => {
    const [c] = seriesCards([series(1, "Empty")], [], [], "");
    expect([c.chapterCount, c.volumeCount, c.progress, c.coverImageId, c.editedAt]).toEqual([0, 0, 0, null, null]);
    expect(sizeLabel(c)).toBe("0 ch");
  });

  it("orders titles naturally and filters case-insensitively", () => {
    const S = [series(1, "Vol 10"), series(2, "Vol 9"), series(3, "Other")];
    expect(seriesCards(S, [], [], "").map((c) => c.series.id)).toEqual([3, 2, 1]);
    expect(seriesCards(S, [], [], "VOL").map((c) => c.series.id)).toEqual([2, 1]);
  });

  it("takes the cover from the first volume before loose chapters", () => {
    const V = [volume(20, 1, 2), volume(10, 1, 1)];
    const D = [
      doc(1, 1, null, { cover_image_id: 100 }),
      doc(2, 1, 20, { cover_image_id: 200 }),
      doc(3, 1, 10, { cover_image_id: undefined, series_order: 9 }),
      doc(4, 1, 10, { cover_image_id: 400, series_order: 10 }),
    ];
    expect(seriesCards([series(1, "A")], D, V, "")[0].coverImageId).toBe(400);
  });

  it("falls back to a loose chapter cover, else null", () => {
    const D = [doc(1, 1, 10), doc(2, 1, null, { cover_image_id: 7 })];
    expect(seriesCards([series(1, "A")], D, [volume(10, 1, 1)], "")[0].coverImageId).toBe(7);
    expect(seriesCards([series(1, "A")], [doc(1, 1, null)], [], "")[0].coverImageId).toBeNull();
  });

  it("computes progress, counts and editedAt", () => {
    const D = [
      doc(1, 1, null, { line_count: 3, translated_count: 1, updated_at: "2026-03-01T00:00:00Z" }),
      doc(2, 1, null, { line_count: 0, translated_count: 0, updated_at: "2026-02-01T00:00:00Z" }),
      doc(3, 2, null, { line_count: 10, translated_count: 10 }),
    ];
    const [c] = seriesCards([series(1, "A")], D, [volume(10, 1, 1)], "");
    expect([c.progress, c.chapterCount, c.volumeCount, c.editedAt]).toEqual([33, 2, 1, "2026-03-01T00:00:00Z"]);
  });
});

describe("sizeLabel", () => {
  it("formats volumes and chapters", () => {
    const c = (volumeCount: number, chapterCount: number) => ({ volumeCount, chapterCount }) as never;
    expect(sizeLabel(c(1, 21))).toBe("1 vol · 21 ch");
    expect(sizeLabel(c(0, 212))).toBe("212 ch");
    expect(sizeLabel(c(3, 5))).toBe("3 vols · 5 ch");
  });
});
