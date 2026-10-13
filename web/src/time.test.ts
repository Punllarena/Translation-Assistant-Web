import { describe, expect, it } from "vitest";
import { defaultSlot, fromLocalInput, toLocalInput } from "./time";

describe("schedule defaults (desktop PublishConfirmDialog)", () => {
  const now = new Date(2026, 9, 13, 21, 15, 30);
  it("uses today's default time when it is still ahead", () => {
    expect(defaultSlot("22:00", now)).toEqual(new Date(2026, 9, 13, 22, 0, 0));
  });
  it("rolls to tomorrow once the default time has passed", () => {
    expect(defaultSlot("20:00", now)).toEqual(new Date(2026, 9, 14, 20, 0, 0));
  });
  it("is an hour from now without a default time", () => {
    expect(defaultSlot("", now).getTime() - now.getTime()).toBe(3_600_000);
  });
});

describe("datetime-local round trip", () => {
  it("formats in local time and parses back to the same instant", () => {
    const d = new Date(2026, 0, 2, 3, 4);
    expect(toLocalInput(d)).toBe("2026-01-02T03:04");
    expect(fromLocalInput("2026-01-02T03:04")).toBe(d.toISOString());
  });
});
