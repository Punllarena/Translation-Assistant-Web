import { describe, expect, it } from "vitest";
import { nextStart, summary, type ScheduleValue } from "./schedule";

const night: ScheduleValue = { enabled: true, start: "22:00", end: "06:00", days: [0, 1, 2, 3, 4, 5, 6], tz: "Asia/Manila" };

describe("summary", () => {
  it("is Off when missing or disabled", () => {
    expect(summary(undefined)).toBe("Off");
    expect(summary({ ...night, enabled: false })).toBe("Off");
  });
  it("names the window, the days and the zone", () => {
    expect(summary({ ...night, start: "01:00", end: "07:00" })).toBe("01:00–07:00 · every night · Asia/Manila");
    expect(summary({ ...night, days: [0, 2] })).toBe("22:00–06:00 · Mon, Wed · Asia/Manila");
  });
  it("says so when no day is picked", () => {
    expect(summary({ ...night, days: [] })).toBe("22:00–06:00 · no days · Asia/Manila");
  });
});

describe("nextStart", () => {
  it("is null when off or without days", () => {
    expect(nextStart(undefined, new Date())).toBeNull();
    expect(nextStart({ ...night, enabled: false }, new Date())).toBeNull();
    expect(nextStart({ ...night, days: [] }, new Date())).toBeNull();
  });
  it("is later today when the window has not opened", () => {
    // Tue 18:00 in Manila
    expect(nextStart(night, new Date("2026-10-27T10:00:00Z"))?.toISOString()).toBe("2026-10-27T14:00:00.000Z");
  });
  it("is tomorrow's start while a window that crosses midnight is open", () => {
    // Tue 23:00 in Manila, inside Tuesday's window
    expect(nextStart(night, new Date("2026-10-27T15:00:00Z"))?.toISOString()).toBe("2026-10-28T14:00:00.000Z");
    // Wed 02:00 in Manila, still Tuesday's window
    expect(nextStart(night, new Date("2026-10-27T18:00:00Z"))?.toISOString()).toBe("2026-10-28T14:00:00.000Z");
  });
  it("skips days that are not picked", () => {
    // Tue 18:00 Manila; only Wednesday (2)
    expect(nextStart({ ...night, days: [2] }, new Date("2026-10-27T10:00:00Z"))?.toISOString()).toBe("2026-10-28T14:00:00.000Z");
    // only Tuesday, after it started: next Tuesday
    expect(nextStart({ ...night, days: [1] }, new Date("2026-10-27T15:00:00Z"))?.toISOString()).toBe("2026-11-03T14:00:00.000Z");
  });
  it("uses the schedule's zone, not the browser's", () => {
    // New York is UTC-4 on 2026-10-27 (DST ends 11-01)
    const ny = { ...night, tz: "America/New_York" };
    expect(nextStart(ny, new Date("2026-10-27T10:00:00Z"))?.toISOString()).toBe("2026-10-28T02:00:00.000Z");
  });
});
