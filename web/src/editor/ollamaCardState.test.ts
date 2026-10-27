import { describe, expect, it } from "vitest";
import type { Schemas } from "../api/client";
import { apply, badge, cardState, initial, lineRange, summary, type StreamState } from "./ollamaCardState";

const sug = (over: Partial<Schemas["SuggestionOut"]> = {}): Schemas["SuggestionOut"] => ({
  line_number: 12, text: "Hello.", stale: false, chunk_id: 3, first_line: 9, last_line: 23,
  model: "qwen3:14b", created_at: new Date(2026, 9, 26, 2, 14).toISOString(), ...over,
});

describe("stream events", () => {
  it("records the plan, waits, then runs on the first thinking or line", () => {
    let s: StreamState = { ...initial, status: "running" };
    s = apply(s, "plan", { first_line: 9, last_line: 23 });
    expect(s).toMatchObject({ status: "running", first: 9, last: 23 });
    s = apply(s, "waiting", { reason: "run" });
    expect(s).toMatchObject({ status: "waiting", reason: "run" });
    s = apply(s, "thinking", { text: "hm" });
    s = apply(s, "thinking", { text: "m" });
    expect(s).toMatchObject({ status: "running", thinking: "hmm" });
    s = apply(s, "line", { line_number: 12, text: "Hi." });
    s = apply(s, "line", { line_number: 13, text: "There." });
    expect(s.lines).toEqual({ 12: "Hi.", 13: "There." });
  });
  it("drops a line's live text on null", () => {
    let s = apply(initial, "line", { line_number: 12, text: "Hi." });
    s = apply(s, "line", { line_number: 12, text: null });
    expect(s.lines[12]).toBeNull();
  });
  it("ends on done, setup or error", () => {
    expect(apply(initial, "done", {}).status).toBe("done");
    expect(apply(initial, "saved", { chunk_ids: [1] }).status).toBe("idle");
    expect(apply(initial, "needs_setup", { message: "No URL" })).toMatchObject({ status: "setup", message: "No URL" });
    expect(apply(initial, "error", { message: "boom" })).toMatchObject({ status: "error", message: "boom" });
  });
});

describe("cardState", () => {
  const running = { ...initial, status: "running" as const };
  it("puts the stream's own states first", () => {
    expect(cardState({ suggestion: sug(), translated: false, stream: running })).toBe("running");
    expect(cardState({ translated: false, stream: { ...initial, status: "waiting", reason: "run" } })).toBe("waiting");
    expect(cardState({ translated: false, stream: { ...initial, status: "waiting", reason: "manual" } })).toBe("manual");
    expect(cardState({ suggestion: sug(), translated: true, stream: { ...initial, status: "error" } })).toBe("error");
    expect(cardState({ translated: false, stream: { ...initial, status: "setup" } })).toBe("setup");
  });
  it("then the saved suggestion, stale when the source changed", () => {
    expect(cardState({ suggestion: sug(), translated: false, stream: initial })).toBe("saved");
    expect(cardState({ suggestion: sug(), translated: true, stream: { ...initial, status: "done" } })).toBe("saved");
    expect(cardState({ suggestion: sug({ stale: true }), translated: false, stream: initial })).toBe("stale");
  });
  it("is idle with nothing saved and nothing running", () => {
    expect(cardState({ translated: true, stream: initial })).toBe("idle");
    expect(cardState({ translated: false, stream: { ...initial, status: "done" } })).toBe("idle");
  });
});

describe("badge", () => {
  it("shows the time today and the date otherwise", () => {
    expect(badge(sug(), new Date(2026, 9, 26, 9, 0))).toBe("prepared 02:14 · qwen3:14b");
    expect(badge(sug(), new Date(2026, 9, 27, 1, 0))).toBe("prepared 2026-10-26 02:14 · qwen3:14b");
  });
});

describe("lineRange", () => {
  it("numbers lines from 1, as the status bar does", () => {
    expect(lineRange(9, 23)).toBe("10–24");
    expect(lineRange(4, 4)).toBe("5");
  });
});

describe("summary", () => {
  const chunk = { model: "qwen3:14b", output_tokens: 500, eval_ms: 20000, total_ms: 31500, prompt_tokens: 1234 };
  it("reads model · tok/s · total s · in / out", () => {
    expect(summary(chunk)).toBe("qwen3:14b · 25.0 tok/s · 31.5 s · 1,234 / 500 tokens");
  });
  it("leaves out what was not measured", () => {
    expect(summary({ ...chunk, eval_ms: null, total_ms: null })).toBe("qwen3:14b · 1,234 / 500 tokens");
    expect(summary({ ...chunk, eval_ms: 0 })).toBe("qwen3:14b · 31.5 s · 1,234 / 500 tokens");
  });
});
