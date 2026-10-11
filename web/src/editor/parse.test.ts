import { describe, expect, it } from "vitest";
import { advanceParse, retreatParse, sentenceRanges } from "./parse";

describe("parse pointer", () => {
  it("advances to the last sentence and stops", () => {
    expect([advanceParse(-1, 2), advanceParse(0, 2), advanceParse(1, 2), advanceParse(-2, 2)]).toEqual([0, 1, 1, -1]);
  });
  it("retreats to -1, or to -2 (raw text) only when the glossary replaced something", () => {
    expect([retreatParse(1, false), retreatParse(-1, false), retreatParse(-1, true), retreatParse(-2, true)]).toEqual([0, -1, -2, -2]);
  });
  it("maps repeated sentences to their own occurrence", () => {
    expect(sentenceRanges("はい、はい、", ["はい", "はい"])).toEqual([[0, 2], [3, 5]]);
  });
  it("marks a sentence it cannot find as empty", () => {
    expect(sentenceRanges("abc", ["zz"])).toEqual([[0, 0]]);
  });
});
