import { describe, expect, it } from "vitest";
import { changedRows, countChanges, moveRow, toEntries } from "./glossary";

const r = (phrase: string, translation = "") => ({ phrase, translation });

describe("glossary rows", () => {
  it("moves a row and stops at the ends", () => {
    expect(moveRow([r("a"), r("b"), r("c")], 1, -1).map((x) => x.phrase)).toEqual(["b", "a", "c"]);
    expect(moveRow([r("a"), r("b")], 0, -1).map((x) => x.phrase)).toEqual(["a", "b"]);
    expect(moveRow([r("a"), r("b")], 1, 1).map((x) => x.phrase)).toEqual(["a", "b"]);
  });
  it("drops fully blank rows only", () => {
    expect(toEntries([r(""), r("a"), r("", "x"), r("  ", " ")])).toEqual([r("a"), r("", "x")]);
  });
  it("marks rows that differ from the loaded glossary at the same position", () => {
    const loaded = [r("a", "x"), r("b", "y")];
    expect([...changedRows(loaded, loaded)]).toEqual([]);
    expect([...changedRows([r("a", "x"), r("b", "z")], loaded)]).toEqual([1]);
    expect([...changedRows([r("b", "y"), r("a", "x")], loaded)]).toEqual([0, 1]);
    expect([...changedRows([...loaded, r("")], loaded)]).toEqual([2]);
  });
  it("counts changed and added rows plus rows removed", () => {
    const loaded = [r("a"), r("b"), r("c")];
    expect(countChanges(loaded, loaded)).toBe(0);
    expect(countChanges([r("a")], loaded)).toBe(2);
    expect(countChanges([r("b"), r("c")], loaded)).toBe(3);
    expect(countChanges([...loaded, r("d")], loaded)).toBe(1);
  });
});
