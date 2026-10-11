import { describe, expect, it } from "vitest";
import { moveRow, toEntries } from "./glossary";

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
});
