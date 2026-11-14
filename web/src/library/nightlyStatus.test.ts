import { describe, expect, it } from "vitest";
import { nightlyNote } from "./nightlyStatus";

const base = { syosetu_url: "https://ncode.syosetu.com/n1/", status: "ongoing", archived_at: null, syosetu_nightly: true };

describe("nightlyNote", () => {
  it("is null for an eligible series", () => {
    expect(nightlyNote(base)).toBeNull();
  });
  it("is null with no syosetu URL (the section is hidden)", () => {
    expect(nightlyNote({ ...base, syosetu_url: "", syosetu_nightly: false })).toBeNull();
  });
  it("says why a series is skipped", () => {
    expect(nightlyNote({ ...base, status: "on_hold" })).toBe("Skipped: the series is not Ongoing.");
    expect(nightlyNote({ ...base, archived_at: "2026-01-01T00:00:00Z" })).toBe("Skipped: the series is archived.");
  });
  it("switched off wins over the other reasons", () => {
    expect(nightlyNote({ ...base, status: "dropped", archived_at: "2026-01-01T00:00:00Z", syosetu_nightly: false }))
      .toBe("Off for this series.");
  });
});
