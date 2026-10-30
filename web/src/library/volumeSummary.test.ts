import { describe, expect, it } from "vitest";
import type { Doc } from "./shelf";
import { summaryText, volumeSummary } from "./volumeSummary";

const now = new Date("2026-11-01T12:00:00Z");

const doc = (id: number, over: Partial<Doc> = {}) =>
  ({ id, line_count: 0, translated_count: 0, wp_status: "", wp_scheduled_for: null, wp_published_at: null, ...over }) as Doc;

describe("volumeSummary", () => {
  it("summary text with WordPress", () => {
    expect(summaryText(
      { chapters: 42, progress: 68, posted: 30, scheduled: 5, next: "2026-11-02T09:00:00Z" },
      true, () => "Nov 2, 18:00",
    )).toBe("42 chapters · 68% translated · 30 posted · 5 scheduled (next: Nov 2, 18:00)");
  });

  it("without WordPress, and nothing scheduled", () => {
    expect(summaryText(
      { chapters: 1, progress: 0, posted: 0, scheduled: 0, next: null }, false, String,
    )).toBe("1 chapter · 0% translated");
  });

  it("a passed schedule counts as posted", () => {
    const docs = [
      doc(1, { wp_status: "future", wp_scheduled_for: "2026-10-31T00:00:00Z", line_count: 4, translated_count: 2 }),
      doc(2, { wp_status: "future", wp_scheduled_for: "2026-11-02T09:00:00Z" }),
      doc(3, { wp_status: "publish", wp_published_at: "2026-10-01T00:00:00Z" }),
      doc(4),
    ];
    expect(volumeSummary(docs, now)).toEqual({
      chapters: 4, progress: 50, posted: 2, scheduled: 1, next: "2026-11-02T09:00:00Z",
    });
  });

  it("takes the earliest scheduled time", () => {
    const docs = [
      doc(1, { wp_status: "future", wp_scheduled_for: "2026-11-05T00:00:00Z" }),
      doc(2, { wp_status: "future", wp_scheduled_for: "2026-11-03T00:00:00Z" }),
    ];
    expect(volumeSummary(docs, now).next).toBe("2026-11-03T00:00:00Z");
  });
});
