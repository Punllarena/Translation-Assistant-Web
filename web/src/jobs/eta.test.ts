import { describe, expect, it } from "vitest";
import { countLine, estimateLeft, formatDuration, leftText, nextSamples } from "./eta";

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

describe("nextSamples", () => {
  const queued = { state: "queued", progress: 0, total: 0 };
  const running = { state: "running", progress: 0, total: 100 };
  it("restarts when a long-queued job starts, so its wait is not counted as no progress", () => {
    const waited = nextSamples(nextSamples(null, queued, 0), queued, 180_000);
    const started = nextSamples(waited, running, 180_500);
    expect(started.first).toEqual({ at: 180_500, done: 0 });
    expect(started.last).toEqual({ at: 180_500, done: 0 });
  });
  it("moves only the last sample while counting", () => {
    const a = nextSamples(null, running, 0);
    const b = nextSamples(a, { ...running, progress: 10 }, 5_000);
    expect(b.first).toEqual({ at: 0, done: 0 });
    expect(b.last).toEqual({ at: 5_000, done: 10 });
    expect(nextSamples(b, { ...running, progress: 10 }, 9_000)).toBe(b);
  });
  it("restarts when the total changes (a refused dry run starts over)", () => {
    const a = nextSamples(nextSamples(null, running, 0), { ...running, progress: 50 }, 5_000);
    expect(nextSamples(a, { ...running, progress: 0, total: 200 }, 6_000).first).toEqual({ at: 6_000, done: 0 });
  });
});

describe("estimate window", () => {
  it("follows the recent rate after a slow phase, not the average since the start", () => {
    const job = { state: "running", total: 100_000 };
    let s = nextSamples(null, { ...job, progress: 0 }, 0);
    s = nextSamples(s, { ...job, progress: 1_600 }, 25_000);   // slow phase: 64 rows/s
    s = nextSamples(s, { ...job, progress: 31_600 }, 35_000);  // fast phase: 3,000 rows/s
    s = nextSamples(s, { ...job, progress: 61_600 }, 45_000);
    s = nextSamples(s, { ...job, progress: 91_600 }, 55_000);
    // the window holds the last 30 s (the 25 s point onwards): 90,000 rows in 30 s
    expect(s.first).toEqual({ at: 25_000, done: 1_600 });
    expect(estimateLeft(s.first, s.last, job.total)).toBeCloseTo(2_800, -1);
  });
});
