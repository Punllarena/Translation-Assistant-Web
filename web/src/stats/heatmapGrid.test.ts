import { describe, expect, it } from "vitest";
import { intensity, thresholds, weeks } from "./heatmapGrid";

describe("weeks (desktop HeatmapWidget layout)", () => {
  const grid = weeks("2026-10-13"); // a Tuesday
  it("has 52 Sunday-first columns ending with today's week", () => {
    expect(grid).toHaveLength(52);
    expect(grid[51]).toEqual(["2026-10-11", "2026-10-12", "2026-10-13", null, null, null, null]);
    expect(grid[0][0]).toBe("2025-10-19");
  });
});

describe("intensity (desktop quartiles of the max)", () => {
  it("is 0 for no work and 1–4 by quartile", () => {
    const th = thresholds([0, 4, 8]);
    expect(th).toEqual([0, 2, 4, 6, 8]);
    expect([0, 1, 2, 5, 8].map((v) => intensity(v, th))).toEqual([0, 1, 1, 2, 4]);
  });
  it("uses fixed steps when there is no data", () => {
    expect(thresholds([])).toEqual([0, 1, 2, 3, 4]);
  });
});
