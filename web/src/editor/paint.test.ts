import { describe, expect, it } from "vitest";
import { jpSpans, segments } from "./paint";

describe("paint", () => {
  it("classifies runs of kanji, hiragana, katakana and Japanese punctuation", () => {
    expect(jpSpans("漢字とカナー、abc")).toEqual([
      { from: 0, to: 2, cls: "jp-kanji" },
      { from: 2, to: 3, cls: "jp-hiragana" },
      { from: 3, to: 6, cls: "jp-katakana" },
      { from: 6, to: 7, cls: "jp-punct" },
    ]);
  });
  it("counts astral kanji as two UTF-16 units", () => {
    expect(jpSpans("𠮷野")).toEqual([{ from: 0, to: 3, cls: "jp-kanji" }]);
  });
  it("segments overlapping spans into classed pieces", () => {
    expect(segments("abcdef", [{ from: 1, to: 4, cls: "x" }, { from: 3, to: 5, cls: "y" }])).toEqual([
      { text: "a", classes: [] },
      { text: "bc", classes: ["x"] },
      { text: "d", classes: ["x", "y"] },
      { text: "e", classes: ["y"] },
      { text: "f", classes: [] },
    ]);
  });
  it("clamps spans to the text and ignores empty ones", () => {
    expect(segments("ab", [{ from: 1, to: 9, cls: "x" }, { from: 0, to: 0, cls: "z" }])).toEqual([
      { text: "a", classes: [] },
      { text: "b", classes: ["x"] },
    ]);
  });
});
