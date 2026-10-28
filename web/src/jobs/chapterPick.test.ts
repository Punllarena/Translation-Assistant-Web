import { describe, expect, it } from "vitest";
import type { Doc, Volume } from "../library/shelf";
import { pickGroups, toggleAll } from "./chapterPick";

const volume = (id: number, volume_order: number, label: string) => ({ id, series_id: 1, volume_order, label }) as Volume;
const doc = (id: number, volume_id: number | null, title: string, o: Partial<Doc> = {}) =>
  ({ id, series_id: 1, volume_id, title, series_order: id, line_count: 10, translated_count: 0, is_illustrations: false, ...o }) as Doc;

describe("pickGroups", () => {
  const V = [volume(2, 2, "Vol. 2"), volume(1, 1, "Vol. 1")];
  const D = [
    doc(4, null, "Afterword"), doc(3, 2, "Prologue"), doc(1, 1, "Illustrations", { is_illustrations: true, line_count: 0 }),
    doc(2, 1, "Chapter One", { translated_count: 4 }), doc(5, 1, "Chapter Two", { translated_count: 10 }), doc(9, 1, "Elsewhere", { series_id: 7 }),
  ];

  it("groups by volume in reading order and numbers chapters, without the Illustrations chapter", () => {
    const g = pickGroups(1, D, V, false, "");
    expect(g.map((x) => x.label)).toEqual(["Vol. 1", "Vol. 2", "No volume"]);
    expect(g[0].rows.map((r) => [r.doc.id, r.number, r.left])).toEqual([[2, 1, 6], [5, 2, 0]]);
  });

  it("narrows to matching titles and drops emptied groups", () => {
    const g = pickGroups(1, D, V, false, "  chapter ");
    expect(g.map((x) => x.label)).toEqual(["Vol. 1"]);
    expect(g[0].rows.map((r) => r.doc.id)).toEqual([2, 5]);
  });

  it("uses syosetu's chapter numbers", () => {
    expect(pickGroups(1, D, V, true, "")[0].rows.map((r) => r.number)).toEqual([2, 5]);
  });
});

describe("toggleAll", () => {
  it("ticks the missing ones, or unticks when all are ticked", () => {
    expect([...toggleAll(new Set([1]), [1, 2])].sort()).toEqual([1, 2]);
    expect([...toggleAll(new Set([1, 2, 3]), [1, 2])]).toEqual([3]);
  });
});
