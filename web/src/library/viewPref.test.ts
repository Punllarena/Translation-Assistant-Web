import { describe, expect, it } from "vitest";
import { parseView, readView, writeView } from "./viewPref";

describe("viewPref", () => {
  it("parseView accepts only list", () => {
    expect(parseView("list")).toBe("list");
    expect(parseView("shelf")).toBe("shelf");
    expect(parseView("grid")).toBe("shelf");
    expect(parseView(null)).toBe("shelf");
    expect(parseView(["list"])).toBe("shelf");
  });

  it("defaults to shelf and survives a throwing storage", () => {
    const boom = () => { throw new Error("blocked"); };
    expect(readView({ getItem: () => null })).toBe("shelf");
    expect(readView({ getItem: () => "weird" })).toBe("shelf");
    expect(readView({ getItem: () => "list" })).toBe("list");
    expect(readView({ getItem: boom })).toBe("shelf");
    expect(() => writeView("list", { setItem: boom })).not.toThrow();
  });

  it("writes under ta.libraryView", () => {
    const seen: string[] = [];
    writeView("list", { setItem: (k, v) => void seen.push(k, v) });
    expect(seen).toEqual(["ta.libraryView", "list"]);
  });
});
