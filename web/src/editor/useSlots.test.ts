import { describe, expect, it } from "vitest";
import { assignSlots } from "./useSlots";

describe("use slots", () => {
  it("gives translation memory 1 and 2, then one slot per backend that can be used", () => {
    expect(assignSlots(["deepl", "mecab", "jparser", "ollama"])).toEqual({ tm: [1, 2], backends: { deepl: 3, ollama: 4 } });
  });

  it("gives nothing to the analysers, which have no Use button", () => {
    expect(assignSlots(["mecab"]).backends).toEqual({});
    expect(assignSlots(["jparser", "mecab"]).tm).toEqual([1, 2]);
  });

  it("keeps a backend's slot as others come and go", () => {
    expect(assignSlots(["deepl", "ollama"]).backends).toEqual({ deepl: 3, ollama: 4 });
    expect(assignSlots(["libretranslate", "deepl", "ollama"]).backends).toEqual({ libretranslate: 3, deepl: 4, ollama: 5 });
  });
});
