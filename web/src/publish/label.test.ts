import { describe, expect, it } from "vitest";
import { confirmLabel, statusTone } from "./label";

describe("publish dialog labels", () => {
  it("says anyway only when the previous chapter is still scheduled", () => {
    expect(confirmLabel(false, false)).toBe("Publish");
    expect(confirmLabel(false, true)).toBe("Publish");
    expect(confirmLabel(true, true)).toBe("Schedule anyway");
    expect(confirmLabel(true, false)).toBe("Publish anyway");
  });
  it("colours published and scheduled, and nothing else", () => {
    expect(statusTone("publish")).toBe("ok");
    expect(statusTone("future")).toBe("warn");
    expect(statusTone("draft")).toBe("");
    expect(statusTone("")).toBe("");
  });
});
