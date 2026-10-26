import { describe, expect, it } from "vitest";
import { PRESETS, presetFor } from "./ollamaPresets";

describe("ollama presets", () => {
  it("matches each preset's numbers", () => {
    expect(presetFor(12, 5)).toBe("small");
    expect(presetFor(25, 10)).toBe("medium");
    expect(presetFor(0, 0)).toBe("large");
  });
  it("falls back to custom for anything else", () => {
    expect(presetFor(12, 6)).toBe("custom");
    expect(presetFor(0, 5)).toBe("custom");
  });
  it("labels the presets", () => {
    expect(PRESETS.small.label).toBe("Small CPU (≈2B)");
    expect(PRESETS.medium.label).toBe("Medium (4–8B)");
    expect(PRESETS.large.label).toBe("Large / GPU");
    expect(PRESETS.custom.label).toBe("Custom");
  });
});
