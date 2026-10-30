import { describe, expect, it } from "vitest";
import type { Doc } from "./shelf";
import { quickPick } from "./chapterPicks";
import { rangeToggle } from "./rangeToggle";

const doc = (id: number, progress: number, wp_status: string) =>
  ({ id, progress, wp_status }) as Doc;

describe("chapterPicks", () => {
  it("untranslated and unposted picks", () => {
    const docs = [doc(1, 100, "publish"), doc(2, 40, "")];
    expect([...quickPick(docs, "untranslated")]).toEqual([2]);
    expect([...quickPick(docs, "unposted")]).toEqual([2]);
    expect(quickPick(docs, "none").size).toBe(0);
    expect([...quickPick(docs, "all")]).toEqual([1, 2]);
  });

  it("range over shown rows only", () => {
    // order = ids of rendered rows (closed blocks excluded)
    expect([...rangeToggle([1, 2, 5, 6], new Set([1]), 6, 1, true)].sort()).toEqual([1, 2, 5, 6]);
    expect([...rangeToggle([1, 2, 5, 6], new Set([1, 2]), 5, 1, true)].sort()).toEqual([1, 2, 5]);
    // the anchor is outside the shown rows: only the clicked row toggles
    expect([...rangeToggle([5, 6], new Set(), 6, 1, true)]).toEqual([6]);
  });
});
