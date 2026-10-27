import { describe, expect, it } from "vitest";
import { barHeights, outcomePcts } from "./ollamaBars";

describe("barHeights", () => {
  it("scales to the tallest bar", () => {
    expect(barHeights([5, 10, 2.5])).toEqual([50, 100, 25]);
  });
  it("gives missing and zero values no height", () => {
    expect(barHeights([null, 0, 4])).toEqual([0, 0, 100]);
  });
  it("is all zero without data", () => {
    expect(barHeights([])).toEqual([]);
    expect(barHeights([null, null])).toEqual([0, 0]);
  });
});

describe("outcomePcts", () => {
  it("is null with no outcomes", () => {
    expect(outcomePcts({ used: 0, edited: 0, ignored: 0 })).toBeNull();
  });
  it("rounds each share of the total", () => {
    expect(outcomePcts({ used: 1, edited: 1, ignored: 2 })).toEqual({ used: 25, edited: 25, ignored: 50 });
  });
});
