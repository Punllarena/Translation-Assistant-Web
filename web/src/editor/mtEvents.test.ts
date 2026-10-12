import { describe, expect, it } from "vitest";
import { apply, initial } from "./mtEvents";

describe("mt events", () => {
  it("accumulates chunks and thinking, then completes", () => {
    let s = { ...initial, status: "running" as const };
    s = apply(s, "thinking", { text: "hm" });
    s = apply(s, "chunk", { text: "a\n\nb" });
    s = apply(s, "chunk", { text: "!" });
    s = apply(s, "done", { cached: false });
    expect(s).toMatchObject({ status: "done", text: "a\n\nb!", thinking: "hm", cached: false });
  });
  it("takes a whole result, analysis entries, setup and errors", () => {
    expect(apply(initial, "result", { text: "x" }).text).toBe("x");
    expect(apply(initial, "analysis", { entries: [{ surface: "猫" }] }).entries).toHaveLength(1);
    expect(apply(initial, "needs_setup", { message: "Add a key" })).toMatchObject({ status: "setup", message: "Add a key" });
    expect(apply(initial, "error", { message: "HTTP 403" })).toMatchObject({ status: "error", message: "HTTP 403" });
  });
  it("ignores unknown event types", () => {
    expect(apply(initial, "weird", {})).toBe(initial);
  });
});
