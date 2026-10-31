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
    expect(bindingOf({ ...key("Enter"), isComposing: false, keyCode: 229 })).toBeNull();
    expect(bindingOf({ ...key("Enter"), keyCode: 13 })).toBe("Enter");
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
  it("refuses bare editing keys, allows them with Ctrl or Alt, and reserves Ctrl+PageUp/Down", () => {
    const b = effective({});
    for (const x of ["Tab", "Backspace", "Delete", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"]) {
      expect(bindingProblem(b, "find", x)).toMatch(/would break typing/);
      expect(bindingProblem(b, "find", `Shift+${x}`)).toMatch(/would break typing/);
    }
    expect(bindingProblem(b, "find", "Alt+ArrowLeft")).toBeNull();
    expect(bindingProblem(b, "find", "Ctrl+Backspace")).toBeNull();
    expect(bindingProblem(b, "find", "Ctrl+PageUp")).toMatch(/reserved/);
    expect(bindingProblem(b, "find", "Ctrl+PageDown")).toMatch(/reserved/);
  });
  it("accepts every default binding for its own action", () => {
    const b = effective({});
    for (const a of ACTIONS) expect(bindingProblem(b, a.key, a.binding)).toBeNull();
  });
  it("refuses bare printable keys but allows named keys and modified ones", () => {
    const b = effective({});
    for (const x of ["A", "Shift+A", "Space", "1", "Shift+Space"]) {
      expect(bindingProblem(b, "next", x)).toMatch(/needs Ctrl or Alt/);
    }
    for (const x of ["Enter", "PageDown", "F1", "PageUp", "Escape", "Ctrl+A", "Alt+Space", "Shift+Enter"]) {
      expect(bindingProblem(b, "add_word", x)?.match(/needs Ctrl/)).toBeFalsy();
    }
  });
});

describe("new action defaults", () => {
  it("give each suggestion its own key", () => {
    expect(effective({}).use_1).toBe("Alt+1");
    expect(effective({}).use_9).toBe("Alt+9");
  });
});
