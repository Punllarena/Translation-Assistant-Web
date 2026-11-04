import { describe, expect, it } from "vitest";
import { readAidsOpen, writeAidsOpen } from "./aidsPref";

function store() {
  const held = new Map<string, string>();
  return {
    held,
    getItem: (k: string) => held.get(k) ?? null,
    setItem: (k: string, v: string) => void held.set(k, v),
  };
}

describe("aids column preference", () => {
  it("starts folded on a narrow screen unless a choice is stored", () => {
    expect(readAidsOpen(store(), true)).toBe(false);
    const s = store();
    writeAidsOpen(true, s);
    expect(readAidsOpen(s, true)).toBe(true);
  });
  it("starts open when nothing is stored", () => {
    expect(readAidsOpen(store())).toBe(true);
  });

  it("remembers a closed column", () => {
    const s = store();
    writeAidsOpen(false, s);
    expect(s.held.get("ta.aidsOpen")).toBe("false");
    expect(readAidsOpen(s)).toBe(false);
  });

  it("remembers an open column", () => {
    const s = store();
    writeAidsOpen(true, s);
    expect(readAidsOpen(s)).toBe(true);
  });

  it("falls back to open when storage throws", () => {
    expect(readAidsOpen({ getItem: () => { throw new Error("blocked"); } })).toBe(true);
    expect(() => writeAidsOpen(false, { setItem: () => { throw new Error("blocked"); } })).not.toThrow();
  });
});
