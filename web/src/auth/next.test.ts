import { describe, expect, it } from "vitest";
import { safeNext } from "./next";

describe("safeNext", () => {
  it("keeps an in-app path with its query", () => {
    expect(safeNext("/series/3?tab=volumes")).toBe("/series/3?tab=volumes");
  });
  it.each([null, "", "https://evil.example", "//evil.example", "/\\evil.example", "series"])(
    "falls back to / for %s",
    (next) => expect(safeNext(next)).toBe("/"),
  );
});
