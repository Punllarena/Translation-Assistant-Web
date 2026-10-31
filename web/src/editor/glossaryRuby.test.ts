import { describe, expect, it } from "vitest";
import { marksToRuby, mergeReadings, shownToPlain, type GlossaryMark } from "./glossaryRuby";
import { authorRuby } from "./ruby";

const mark = (from: number, to: number, translation: string, shown_from: number, shown_to: number): GlossaryMark => ({
  from,
  to,
  translation,
  shown_from,
  shown_to,
});

describe("marksToRuby", () => {
  it("places the translation over the mark's range", () => {
    const marks = [mark(0, 2, "Taro", 0, 4)];
    expect(marksToRuby(marks, [])).toEqual([{ from: 0, to: 2, rt: "Taro", cls: "rt-glossary" }]);
  });

  it("drops a mark overlapping an author ruby range or its hidden bracket range", () => {
    // 漢字(かんじ): base [0,2), hidden brackets [2,7)
    const author = authorRuby("漢字(かんじ)");
    expect(author).toHaveLength(1);
    expect(marksToRuby([mark(0, 2, "Kanji", 0, 5)], author)).toEqual([]); // overlaps base
    expect(marksToRuby([mark(3, 4, "x", 0, 1)], author)).toEqual([]); // overlaps hide
    expect(marksToRuby([mark(8, 9, "after", 5, 10)], author)).toEqual([
      { from: 8, to: 9, rt: "after", cls: "rt-glossary" },
    ]); // clear of author
  });
});

describe("mergeReadings", () => {
  it("keeps a reading outside a mark and drops one inside it, sorted by from", () => {
    const glossary = [{ from: 0, to: 2, rt: "Taro", cls: "rt-glossary" }];
    const readings = [
      { from: 3, to: 4, rt: "は" },
      { from: 0, to: 2, rt: "たろう" }, // overlaps the glossary entry → dropped
    ];
    expect(mergeReadings(glossary, readings)).toEqual([
      { from: 0, to: 2, rt: "Taro", cls: "rt-glossary" },
      { from: 3, to: 4, rt: "は" },
    ]);
  });
});

describe("shownToPlain", () => {
  const marks = [mark(0, 2, "Taro", 0, 4)];

  it("maps the left and right edges to the mark's plain range", () => {
    expect(shownToPlain(marks, 0)).toBe(0); // left edge → from
    expect(shownToPlain(marks, 4)).toBe(2); // right edge → to
  });

  it("shifts an offset after the mark by the length difference", () => {
    expect(shownToPlain(marks, 5)).toBe(3); // 5 - (4 - 2)
  });

  it("maps an offset inside the mark by interpolation", () => {
    expect(shownToPlain(marks, 2)).toBe(1); // halfway through shown [0,4) → plain 1
  });

  it("is the identity with no marks", () => {
    expect(shownToPlain([], 7)).toBe(7);
  });
});
