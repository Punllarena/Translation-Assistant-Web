import { describe, expect, it } from "vitest";
import { parseThemePref, readPref, resolveTheme, THEME_KEY } from "./theme";

describe("theme", () => {
  it("parses known preferences and treats anything else as system", () => {
    expect(parseThemePref("light")).toBe("light");
    expect(parseThemePref("dark")).toBe("dark");
    expect(parseThemePref("system")).toBe("system");
    for (const v of [undefined, null, "", "blue", "Dark", 1, true, {}]) expect(parseThemePref(v)).toBe("system");
  });

  it("resolves system from the OS and keeps explicit choices", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
  });

  it("reads the stored preference and survives missing or throwing storage", () => {
    expect(readPref({ getItem: (k: string) => (k === THEME_KEY ? "dark" : null) })).toBe("dark");
    expect(readPref({ getItem: () => null })).toBe("system");
    expect(readPref(null)).toBe("system");
    expect(readPref({ getItem: () => { throw new Error("SecurityError"); } })).toBe("system");
  });
});
