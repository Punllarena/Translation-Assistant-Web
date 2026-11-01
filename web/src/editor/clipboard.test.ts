import { describe, expect, it } from "vitest";
import { unsavedText } from "./clipboard";

describe("unsaved text", () => {
  it("writes one block per line, in line order", () => {
    expect(unsavedText([
      { line_number: 3, translated_text: "d" },
      { line_number: 0, translated_text: "a" },
    ])).toBe("Line 1\na\n\nLine 4\nd");
  });

  it("writes nothing when nothing is unsaved", () => {
    expect(unsavedText([])).toBe("");
  });
});
