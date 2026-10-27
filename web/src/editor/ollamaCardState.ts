import type { Schemas } from "../api/client";

export type Suggestion = Schemas["SuggestionOut"];

/** One by-hand stream (`GET /documents/{id}/ollama/stream`) folded into a state. */
export type StreamState = {
  status: "idle" | "running" | "waiting" | "done" | "error" | "setup";
  reason: "run" | "manual" | null; // why it waits for the lane
  first: number | null; // the chunk's first and last line numbers
  last: number | null;
  thinking: string;
  lines: Record<number, string | null>; // live text; null: shown, then dropped by the answer check
  message: string;
};

export type CardState = "saved" | "stale" | "running" | "waiting" | "manual" | "error" | "setup" | "idle";

export const initial: StreamState = {
  status: "idle", reason: null, first: null, last: null, thinking: "", lines: {}, message: "",
};

/** Fold one server-sent event into the stream state. */
export function apply(state: StreamState, type: string, data: unknown): StreamState {
  const d = (data ?? {}) as {
    first_line?: number; last_line?: number; reason?: string; text?: string | null;
    line_number?: number; message?: string;
  };
  switch (type) {
    case "plan": return { ...state, first: d.first_line ?? null, last: d.last_line ?? null };
    case "waiting": return { ...state, status: "waiting", reason: d.reason === "manual" ? "manual" : "run" };
    case "thinking": return { ...state, status: "running", thinking: state.thinking + (d.text ?? "") };
    case "line":
      if (typeof d.line_number !== "number") return state;
      return { ...state, status: "running", lines: { ...state.lines, [d.line_number]: d.text ?? null } };
    case "needs_setup": return { ...state, status: "setup", message: d.message ?? "" };
    case "error": return { ...state, status: "error", message: d.message ?? "" };
    case "done": return { ...state, status: "done" };
    default: return state; // saved: the caller refetches the suggestions
  }
}

/** What the card shows: the stream's own states first, then the saved suggestion. */
export function cardState(input: { suggestion?: Suggestion; translated: boolean; stream: StreamState }): CardState {
  const { suggestion, stream } = input;
  switch (stream.status) {
    case "setup": return "setup";
    case "error": return "error";
    case "waiting": return stream.reason === "manual" ? "manual" : "waiting";
    case "running": return "running";
  }
  if (suggestion) return suggestion.stale ? "stale" : "saved";
  return "idle"; // translated or not, nothing saved: the card offers Translate chunk
}

const p2 = (n: number) => String(n).padStart(2, "0");

/** "prepared 02:14 · qwen3:14b", with the local date when it was not made today. */
export function badge(s: Suggestion, now: Date): string {
  const d = new Date(s.created_at);
  const time = `${p2(d.getHours())}:${p2(d.getMinutes())}`;
  const today = d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate();
  const when = today ? time : `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())} ${time}`;
  return `prepared ${when} · ${s.model}`;
}

/** A chunk's lines as the editor numbers them (from 1). */
export function lineRange(first: number, last: number): string {
  return first === last ? String(first + 1) : `${first + 1}–${last + 1}`;
}

/** The Reasoning tab's one-line summary: model · tok/s · total s · in / out tokens. */
export function summary(c: Pick<Schemas["ChunkOut"], "model" | "output_tokens" | "eval_ms" | "total_ms" | "prompt_tokens">): string {
  const parts = [c.model];
  if (c.eval_ms) parts.push(`${((c.output_tokens / c.eval_ms) * 1000).toFixed(1)} tok/s`);
  if (c.total_ms !== null) parts.push(`${(c.total_ms / 1000).toFixed(1)} s`);
  parts.push(`${c.prompt_tokens.toLocaleString("en-US")} / ${c.output_tokens.toLocaleString("en-US")} tokens`);
  return parts.join(" · ");
}
