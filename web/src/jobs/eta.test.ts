import { describe, expect, it } from "vitest";
import { countLine, estimateLeft, formatDuration, leftText } from "./eta";

describe("countLine", () => {
  it("is just the message while nothing is counted (total 0)", () => {
    expect(countLine({ message: "Starting", progress: 0, total: 0 })).toBe("Starting");
  });
  it("is just the message for a single step (total 1)", () => {
    expect(countLine({ message: "Checking the library", progress: 0, total: 1 })).toBe("Checking the library");
  });
  it("shows counts and a whole percent", () => {
    expect(countLine({ message: "Checking lines", progress: 71330, total: 482456 }))
      .toBe("Checking lines · 71,330 of 482,456 (15%)");
  });
});

describe("formatDuration", () => {
  it("formats seconds, minutes and hours", () => {
    expect(formatDuration(42_000)).toBe("42 s");
    expect(formatDuration(7 * 60_000 + 20_000)).toBe("7 min");
    expect(formatDuration(65 * 60_000)).toBe("1 h 5 min");
  });
});

describe("estimateLeft", () => {
  const first = { at: 0, done: 0 };
  it("waits for 10 s of samples", () => {
    expect(estimateLeft(first, { at: 9_999, done: 500 }, 1000)).toBeNull();
  });
  it("is null without progress", () => {
    expect(estimateLeft(first, { at: 20_000, done: 0 }, 1000)).toBeNull();
  });
  it("is null for an uncounted job (total 0 or 1)", () => {
    expect(estimateLeft(first, { at: 20_000, done: 1 }, 1)).toBeNull();
    expect(estimateLeft(first, { at: 20_000, done: 0 }, 0)).toBeNull();
  });
  it("projects the observed rate over what is left", () => {
    // 100 rows in 10 s = 10 rows/s; 900 left = 90 s
    expect(estimateLeft(first, { at: 10_000, done: 100 }, 1000)).toBe(90_000);
  });
});

describe("leftText", () => {
  it("rounds to words", () => {
    expect(leftText(30_000)).toBe("under a minute left");
    expect(leftText(45 * 60_000)).toBe("about 45 min left");
    expect(leftText(null)).toBeNull();
  });
});
