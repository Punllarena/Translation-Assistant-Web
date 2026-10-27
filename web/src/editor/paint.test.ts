import { describe, expect, it } from "vitest";
import { jpSpans, layout, segments, type Piece } from "./paint";
import { authorRuby } from "./ruby";

const drawn = (ps: Piece[]): string =>
  ps.map((p) => (p.kind === "text" ? p.seg.text : p.base.map((s) => s.text).join(""))).join("");

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
  describe("layout", () => {
    const src = "大(おお)きく";
    it("draws author ruby as a ruby piece and hides the bracketed reading", () => {
      const ps = layout(src, [], authorRuby(src));
      expect(ps).toEqual([
        { kind: "ruby", base: [{ text: "大", classes: [] }], rt: "おお", rtClasses: [] },
        { kind: "text", seg: { text: "きく", classes: [] } },
      ]);
      expect(drawn(ps)).not.toMatch(/[()]/);
    });
    it("cuts a span crossing the base edge into one segment inside and one outside", () => {
      const ps = layout(src, [{ from: 0, to: 6, cls: "jp-kanji" }], authorRuby(src));
      expect(ps[0]).toMatchObject({ kind: "ruby", base: [{ text: "大", classes: ["jp-kanji"] }] });
      // the span ends at 6, so it covers き but not く (the text is 7 UTF-16 units)
      expect(ps.slice(1)).toEqual([
        { kind: "text", seg: { text: "き", classes: ["jp-kanji"] } },
        { kind: "text", seg: { text: "く", classes: [] } },
      ]);
      expect(drawn(ps)).toBe("大きく");
    });
    it("marks the reading when a find hit lies inside the hidden range", () => {
      const ps = layout(src, [{ from: 2, to: 4, cls: "find-current" }], authorRuby(src));
      expect(ps[0].kind === "ruby" && ps[0].rtClasses).toContain("find-current");
    });
    it("marks a Latin reading", () => {
      const ps = layout("大きく", [], [{ from: 0, to: 1, rt: "oo" }]);
      expect(ps[0].kind === "ruby" && ps[0].rtClasses).toEqual(["rt-latin"]);
    });
    it("equals segments when there is no ruby", () => {
      const text = "漢字とカナー、abc";
      const spans = [...jpSpans(text), { from: 1, to: 4, cls: "find-current" }];
      expect(layout(text, spans, [])).toEqual(segments(text, spans).map((seg) => ({ kind: "text", seg })));
    });
  });
});
