import { describe, expect, it } from "vitest";
import { pickedInOrder, rangeToggle } from "./rangeToggle";

const order = [10, 11, 12, 13];
const sorted = (s: Set<number>) => [...s].sort((a, b) => a - b);

describe("rangeToggle", () => {
  it("toggles one without an anchor", () => expect(sorted(rangeToggle(order, new Set(), 11, null, true))).toEqual([11]));
  it("ticks a range downwards", () => expect(sorted(rangeToggle(order, new Set([10]), 12, 10, true))).toEqual([10, 11, 12]));
  it("ticks a range upwards", () => expect(sorted(rangeToggle(order, new Set([13]), 11, 13, true))).toEqual([11, 12, 13]));
  it("unticks a range when the clicked one was ticked", () =>
    expect(sorted(rangeToggle(order, new Set([10, 11, 12]), 12, 10, true))).toEqual([]));
  it("toggles off without shift", () => expect(sorted(rangeToggle(order, new Set([10]), 10, 10, false))).toEqual([]));
  it("ignores an anchor that is gone", () => expect(sorted(rangeToggle(order, new Set(), 12, 99, true))).toEqual([12]));
  it("does not mutate its input", () => {
    const picked = new Set([10]);
    rangeToggle(order, picked, 11, null, false);
    expect(sorted(picked)).toEqual([10]);
  });
});

describe("pickedInOrder", () => {
  it("keeps list order and drops ids that are gone", () =>
    expect(pickedInOrder([10, 11, 12], new Set([12, 99, 10]))).toEqual([10, 12]));
});
