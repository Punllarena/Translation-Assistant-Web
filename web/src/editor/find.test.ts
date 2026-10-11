import { describe, expect, it } from "vitest";
import { findHits, findIn, firstFrom, wrapStep } from "./find";

describe("find", () => {
  it("is case-insensitive and escapes regex characters", () => {
    expect(findIn("Taro taro TARO", "taro")).toEqual([[0, 4], [5, 9], [10, 14]]);
    expect(findIn("a.b axb", "a.b")).toEqual([[0, 3]]);
    expect(findIn("abc", "")).toEqual([]);
  });
  it("uses UTF-16 offsets past astral characters", () => {
    expect(findIn("𠮷野家の𠮷", "𠮷")).toEqual([[0, 2], [5, 7]]);
  });
  it("lists source hits before translation hits per line", () => {
    const hits = findHits([{ index: 3, source: "犬", translation: "a dog 犬" }], "犬");
    expect(hits).toEqual([
      { index: 3, field: "source", from: 0, to: 1 },
      { index: 3, field: "translation", from: 6, to: 7 },
    ]);
  });
  it("wraps in both directions and starts from either end", () => {
    expect([wrapStep(2, 3, 1), wrapStep(0, 3, -1), wrapStep(-1, 3, 1), wrapStep(-1, 3, -1), wrapStep(0, 0, 1)]).toEqual([0, 2, 0, 2, -1]);
  });
  it("firstFrom picks the first hit at or after the active line, else the first", () => {
    const hits = [{ index: 1 }, { index: 5 }].map((h) => ({ ...h, field: "source" as const, from: 0, to: 1 }));
    expect([firstFrom(hits, 3), firstFrom(hits, 9), firstFrom([], 0)]).toEqual([1, 0, -1]);
  });
});
