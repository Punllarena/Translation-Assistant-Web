import { describe, expect, it } from "vitest";
import { cutsFromText, firstTextDifference, insertMarker, SPLIT_MARKER } from "./cuts";

const M = SPLIT_MARKER;

describe("split cuts", () => {
  it("cuts before the line after each marker, with its title", () => {
    expect(cutsFromText(`a\nb\n${M} Two\nc\n${M}\nd`)).toEqual([{ start: 2, title: "Two" }, { start: 3, title: "" }]);
  });
  it("ignores a marker before the first line, at the end, or repeated", () => {
    expect(cutsFromText(`${M} x\na\n${M} y\n${M} z\nb\n${M} end`)).toEqual([{ start: 1, title: "y" }]);
  });
  it("inserts a marker at the start of the caret's line and puts the caret after it", () => {
    const { text, caret } = insertMarker("ab\ncd", 4);
    expect(text).toBe(`ab\n${M} \ncd`);
    expect(text.slice(0, caret)).toBe(`ab\n${M} `);
  });
  it("puts the marker on line 1 at caret 0, with or without a leading newline", () => {
    expect(insertMarker("ab", 0).text).toBe(`${M} \nab`);
    expect(insertMarker("\nab", 0).text).toBe(`${M} \n\nab`);
  });
  it("inserts before the caret's own line when the caret is exactly at a line start", () => {
    expect(insertMarker("ab\ncd", 3).text).toBe(`ab\n${M} \ncd`);
    expect(insertMarker("\nab", 1).text).toBe(`\n${M} \nab`);
  });
});

describe("firstTextDifference", () => {
  it("is null when only markers were added", () => {
    expect(firstTextDifference("a\nb\nc", `a\n${M} T\nb\nc`)).toBeNull();
  });
  it("names the first edited line, 1-based, ignoring markers in the count", () => {
    expect(firstTextDifference("a\nb\nc", `a\n${M}\nbX\nc`)).toBe(2);
  });
  it("catches an inserted blank line, which would shift every later cut", () => {
    expect(firstTextDifference("a\nb\nc", `a\n\nb\nc`)).toBe(2);
  });
  it("catches a removed or appended line", () => {
    expect(firstTextDifference("a\nb", "a")).toBe(2);
    expect(firstTextDifference("a", "a\nb")).toBe(2);
  });
});
