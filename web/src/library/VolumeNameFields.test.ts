import { describe, expect, it } from "vitest";
import { kindOptions, listedKind } from "./VolumeNameFields";

describe("listedKind", () => {
  const kinds = kindOptions([{ kind: "Arc" }]);

  it("returns the listed spelling, ignoring case and spaces", () => {
    expect(listedKind(" side story ", kinds)).toBe("Side Story");
    expect(listedKind("arc", kinds)).toBe("Arc");
  });

  it("treats an empty kind as the No kind option", () => {
    expect(listedKind("", kinds)).toBe("");
    expect(listedKind("  ", kinds)).toBe("");
  });

  it("returns null for a kind that is not listed", () => {
    expect(listedKind("Prologue", kinds)).toBeNull();
  });
});
