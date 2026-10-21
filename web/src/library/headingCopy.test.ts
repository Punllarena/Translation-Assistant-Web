import { describe, expect, it } from "vitest";
import { decode, encode, optionLabel, regroupMessage } from "./headingCopy";

describe("headingCopy", () => {
  it("labels markers", () => {
    expect(optionLabel({ marker: "★", headings: 14 })).toBe("Only headings starting with ★ (14 headings)");
    expect(optionLabel({ marker: "◎", headings: 1 })).toBe("Only headings starting with ◎ (1 heading)");
    expect(optionLabel({ marker: "◎", headings: 0 })).toBe("Only headings starting with ◎ (0 headings)");
  });
  it("says what a regroup does", () => {
    expect(regroupMessage({ volumes_created: 20, chapters_moved: 1483, volumes_emptied: 78 }))
      .toBe("Creates 20 volumes and moves 1483 chapters. 78 volumes will be left empty; they're kept so switching back finds them.");
    expect(regroupMessage({ volumes_created: 1, chapters_moved: 1, volumes_emptied: 0 })).toBe("Creates 1 volume and moves 1 chapter.");
    expect(regroupMessage({ volumes_created: 0, chapters_moved: 2, volumes_emptied: 1 }))
      .toBe("Creates 0 volumes and moves 2 chapters. 1 volume will be left empty; they're kept so switching back finds them.");
  });
  it("round-trips the select value", () => {
    expect(decode(encode("marker", "★"))).toEqual({ mode: "marker", marker: "★" });
    expect(decode(encode("all", ""))).toEqual({ mode: "all", marker: "" });
    expect(encode("off", "")).toBe("off");
  });
});
