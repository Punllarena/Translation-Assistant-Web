import { describe, expect, it } from "vitest";
import { anchorFromCardNumber, cardNumberFromAnchor, END } from "./imageMove";

describe("imageMove", () => {
  it("turns a card number into the 0-based anchor", () => {
    expect(anchorFromCardNumber("1")).toBe(0);
    expect(anchorFromCardNumber(" 12 ")).toBe(11);
  });
  it("sends blank, zero and junk to the end", () => {
    for (const t of ["", "0", "-3", "x", "2.5"]) expect(anchorFromCardNumber(t)).toBe(END);
  });
  it("shows the card number, blank past the end", () => {
    expect(cardNumberFromAnchor(0, 5)).toBe("1");
    expect(cardNumberFromAnchor(5, 5)).toBe("");
  });
});
