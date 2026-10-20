import { describe, expect, it } from "vitest";
import { chapterNumber, pickVolume, volumeGroups } from "./volumes";
import type { Doc, Volume } from "./shelf";

const volume = (id: number, series_id: number, volume_order: number) => ({ id, series_id, volume_order }) as Volume;
const doc = (id: number, series_id: number, volume_id: number | null, o: Partial<Doc> = {}) =>
  ({ id, series_id, volume_id, series_order: id, line_count: 0, translated_count: 0, ...o }) as Doc;

describe("volumeGroups", () => {
  it('puts loose chapters last as "none"', () => {
    const V = [volume(2, 1, 2), volume(1, 1, 1), volume(9, 5, 1)];
    const D = [doc(1, 1, null), doc(2, 1, 2, { series_order: 5 }), doc(3, 1, 2, { series_order: 4 }), doc(4, 1, 1), doc(5, 5, 9)];
    const g = volumeGroups(1, D, V);
    expect(g.map((x) => x.key)).toEqual([1, 2, "none"]);
    expect(g[1].docs.map((d) => d.id)).toEqual([3, 2]);
    expect(g[2].volume).toBeNull();
  });

  it("omits an empty none group, yields one for a series with no volumes", () => {
    expect(volumeGroups(1, [doc(1, 1, 1)], [volume(1, 1, 1)]).map((x) => x.key)).toEqual([1]);
    expect(volumeGroups(1, [], []).map((x) => x.key)).toEqual(["none"]);
  });

  it("computes cover and progress per group", () => {
    const D = [doc(1, 1, 1, { line_count: 4, translated_count: 1, cover_image_id: 8 })];
    const [g] = volumeGroups(1, D, [volume(1, 1, 1)]);
    expect([g.coverImageId, g.progress]).toEqual([8, 25]);
  });
});

describe("chapterNumber", () => {
  it("restarts per volume, uses series_order for syosetu", () => {
    const D = [doc(1, 1, 1, { series_order: 40 }), doc(2, 1, 1, { series_order: 41 })];
    const [g] = volumeGroups(1, D, [volume(1, 1, 1)]);
    expect(chapterNumber(g, D[1], false)).toBe(2);
    expect(chapterNumber(g, D[1], true)).toBe(41);
  });
});

describe("pickVolume", () => {
  const groups = volumeGroups(1, [doc(1, 1, null)], [volume(3, 1, 1)]);
  it("falls back to the first group for an unknown id", () => {
    expect(pickVolume("3", groups)).toBe(3);
    expect(pickVolume("none", groups)).toBe("none");
    expect(pickVolume("77", groups)).toBe(3);
    expect(pickVolume(null, groups)).toBe(3);
    expect(pickVolume("1", [])).toBeNull();
  });
});
