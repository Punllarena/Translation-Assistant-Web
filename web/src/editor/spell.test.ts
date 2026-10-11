import { describe, expect, it } from "vitest";
import { spellBatches } from "./spell";

describe("spellBatches", () => {
  it("caps texts per batch", () => {
    expect(spellBatches(["a", "b", "c"], 2)).toEqual([["a", "b"], ["c"]]);
  });
  it("caps characters per batch", () => {
    expect(spellBatches(["aaaa", "bbbb", "cc"], 200, 6)).toEqual([["aaaa"], ["bbbb", "cc"]]);
  });
  it("drops texts the API would refuse and empty ones", () => {
    expect(spellBatches(["x".repeat(100_001), "", "ok"])).toEqual([["ok"]]);
  });
});
