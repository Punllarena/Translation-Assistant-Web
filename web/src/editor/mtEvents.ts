export type Entry = {
  surface: string; reading?: string; lemma?: string; pos?: string; gloss?: string;
  tense?: string; base_form?: string; matched?: boolean;
};

export type MtState = {
  status: "idle" | "running" | "done" | "error" | "setup";
  text: string; thinking: string; entries: Entry[]; message: string; cached: boolean;
};

export const initial: MtState = { status: "idle", text: "", thinking: "", entries: [], message: "", cached: false };

/** Fold one server-sent event into the panel state. */
export function apply(state: MtState, type: string, data: unknown): MtState {
  const d = (data ?? {}) as { text?: string; entries?: Entry[]; message?: string; cached?: boolean };
  switch (type) {
    case "chunk": return { ...state, text: state.text + (d.text ?? "") };
    case "thinking": return { ...state, thinking: state.thinking + (d.text ?? "") };
    case "result": return { ...state, text: d.text ?? "" };
    case "analysis": return { ...state, entries: d.entries ?? [] };
    case "needs_setup": return { ...state, status: "setup", message: d.message ?? "" };
    case "error": return { ...state, status: "error", message: d.message ?? "" };
    case "done": return { ...state, status: "done", cached: Boolean(d.cached) };
    default: return state;
  }
}
