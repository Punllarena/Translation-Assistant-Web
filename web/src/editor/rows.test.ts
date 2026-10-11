import { describe, expect, it } from "vitest";
import {
  buildRows, firstContent, firstUntranslated, hasContent, lineAtOrAfter, nextContent,
  prevContent, progress, sourceText, type Image, type Line,
} from "./rows";

const line = (n: number, raw: string, prefix = "%") =>
  ({ line_number: n, prefix, raw_text: raw, display_text: raw, sentences: [raw], replaced: false, translated_text: "" }) as Line;
const image = (id: number, anchor: number) => ({ id, anchor_position: anchor }) as Image;
const L = [line(0, "一"), line(1, ""), line(2, "二"), line(3, "  "), line(4, "三")];

describe("rows", () => {
  it("hasContent ignores markers and whitespace", () => {
    expect([hasContent("一"), hasContent(""), hasContent("%$ "), hasContent("%$")]).toEqual([true, false, false, false]);
  });
  it("buildRows skips blank lines and anchors images before their line", () => {
    const rows = buildRows(L, [image(9, 99), image(7, 2), image(8, 0)]);
    expect(rows.map((r) => (r.kind === "line" ? `L${r.index}` : `I${r.image.id}`))).toEqual(["I8", "L0", "I7", "L2", "L4", "I9"]);
  });
  it("navigates over translatable lines only", () => {
    expect([nextContent(L, 0), nextContent(L, 2), nextContent(L, 4)]).toEqual([2, 4, null]);
    expect([prevContent(L, 4), prevContent(L, 2), prevContent(L, 0)]).toEqual([2, 0, null]);
    expect(firstContent(L)).toBe(0);
  });
  it("firstUntranslated searches from the top", () => {
    expect(firstUntranslated(L, { 0: "a", 2: "", 4: "" })).toBe(2);
    expect(firstUntranslated(L, { 0: "a", 2: "b", 4: "c" })).toBeNull();
  });
  it("lineAtOrAfter clamps and moves to the next translatable line", () => {
    expect([lineAtOrAfter(L, 1), lineAtOrAfter(L, 2), lineAtOrAfter(L, 99), lineAtOrAfter(L, -5)]).toEqual([0, 2, 4, 0]);
  });
  it("progress counts translatable lines and words of non-empty translations", () => {
    expect(progress(L, { 0: "two words", 2: "", 4: "x" })).toEqual({ percent: 66, words: 3 });
    expect(progress([line(0, "")], {})).toEqual({ percent: 0, words: 0 });
  });
  it("sourceText keeps $ continuations", () => {
    expect(sourceText([line(0, "一。"), line(1, "二。", "$"), line(2, "")])).toBe("一。\n$二。\n");
  });
});
