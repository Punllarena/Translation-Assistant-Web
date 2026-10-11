import { describe, expect, it } from "vitest";
import { ACTIONS, actionOf, bindingOf, bindingProblem, effective, PUNCTUATIONS } from "./keymap";

const key = (k: string, mods: Partial<Record<"ctrlKey" | "altKey" | "shiftKey" | "metaKey", boolean>> = {}) =>
  ({ key: k, ctrlKey: false, altKey: false, shiftKey: false, metaKey: false, ...mods });

describe("keymap", () => {
  it("names key presses", () => {
    expect(bindingOf(key("Enter"))).toBe("Enter");
    expect(bindingOf(key("j", { ctrlKey: true }))).toBe("Ctrl+J");
    expect(bindingOf(key("ArrowRight", { ctrlKey: true, shiftKey: true }))).toBe("Ctrl+Shift+ArrowRight");
    expect(bindingOf(key("=", { metaKey: true }))).toBe("Ctrl+=");
    expect(bindingOf(key(" ", { altKey: true }))).toBe("Alt+Space");
    expect(bindingOf(key("Shift", { shiftKey: true }))).toBeNull();
  });
  it("ignores key presses during IME composition and dead keys", () => {
    expect(bindingOf({ ...key("Enter"), isComposing: true })).toBeNull();
    expect(bindingOf({ ...key("a"), isComposing: true })).toBeNull();
    expect(bindingOf(key("Process"))).toBeNull();
    expect(bindingOf(key("Dead"))).toBeNull();
    expect(bindingOf(key("Unidentified"))).toBeNull();
    expect(bindingOf({ ...key("Enter"), isComposing: false })).toBe("Enter");
  });
  it("has unique action keys and default bindings, nine F-key inserts", () => {
    expect(new Set(ACTIONS.map((a) => a.key)).size).toBe(ACTIONS.length);
    expect(new Set(ACTIONS.map((a) => a.binding)).size).toBe(ACTIONS.length);
    expect(PUNCTUATIONS).toHaveLength(9);
    expect(effective({}).punct_8).toBe("F9");
  });
  it("overrides replace defaults", () => {
    const b = effective({ next: "Ctrl+K" });
    expect([b.next, actionOf(b, "Ctrl+K"), actionOf(b, "PageDown")]).toEqual(["Ctrl+K", "next", undefined]);
  });
  it("refuses a binding another action uses, including a default", () => {
    const b = effective({});
    expect(bindingProblem(b, "next", "Ctrl+J")).toMatch(/already used by/);
    expect(bindingProblem(b, "add_word", "Ctrl+J")).toBeNull();
    expect(bindingProblem(b, "next", "Ctrl+K")).toBeNull();
  });
  it("refuses browser-reserved bindings", () => {
    expect(bindingProblem(effective({}), "next", "Ctrl+W")).toMatch(/reserved/);
  });
});
