import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { api, call } from "../api/client";
import { apply, badge, cardState, initial, lineRange, type StreamState, type Suggestion } from "./ollamaCardState";
import ReasoningDialog from "./ReasoningDialog";

const EVENTS = ["plan", "waiting", "thinking", "line", "saved", "needs_setup", "error", "done"];
const TERMINAL = new Set(["needs_setup", "error", "done"]);

/** A request for the chunk holding `line`; `n` makes a repeat (Retry, a second click) a new one. */
type Want = { line: number; reroll: boolean; n: number };

/** The by-hand stream for `want`. Closing it (a new want, the card unmounting) leaves the
 * chunk running on the server; asking again for a line of it follows it. */
function useOllamaStream(documentId: number, want: Want | null, onSaved: () => void): StreamState {
  const [state, setState] = useState<StreamState>(initial);
  const saved = useRef(onSaved);
  saved.current = onSaved;
  useEffect(() => {
    if (!want) { setState(initial); return; }
    setState({ ...initial, status: "running" });
    let es: EventSource | null = null;
    const timer = setTimeout(() => {
      const params = new URLSearchParams({ line_number: String(want.line), reroll: String(want.reroll) });
      const source = new EventSource(`/api/documents/${documentId}/ollama/stream?${params}`);
      es = source;
      let heard = false;
      let terminal = false;
      for (const type of EVENTS) {
        source.addEventListener(type, (e) => {
          heard = true;
          let data: unknown = {};
          try { data = JSON.parse((e as MessageEvent).data); } catch { /* keep {} */ }
          setState((s) => apply(s, type, data));
          if (type === "saved" || type === "done") saved.current();
          if (TERMINAL.has(type)) { terminal = true; source.close(); }
        });
      }
      source.onerror = () => {
        if (!terminal) setState((s) => apply(s, "error", { message: heard ? "Connection lost" : "Connection failed" }));
        source.close();
      };
    }, 300);
    return () => { clearTimeout(timer); es?.close(); };
  }, [documentId, want]);
  return state;
}

/** The Ollama card: the line's saved suggestion (Use / Reasoning / Reroll), or by-hand
 * translation of the chunk the line belongs to, streamed line by line. */
export default function OllamaCard({ documentId, lineNumber, translated, onUse }: {
  documentId: number; lineNumber: number; translated: boolean; onUse(text: string): void;
}) {
  const queryClient = useQueryClient();
  const sugs = useQuery({
    queryKey: ["ollama", documentId],
    queryFn: () => call(api.GET("/documents/{document_id}/ollama", { params: { path: { document_id: documentId } } })),
  });
  const refresh = useCallback(
    () => void queryClient.invalidateQueries({ queryKey: ["ollama", documentId] }), [queryClient, documentId]);
  const suggestion = sugs.data?.find((s) => s.line_number === lineNumber);
  const [want, setWant] = useState<Want | null>(null);
  const [reasoning, setReasoning] = useState<number | null>(null);
  const translatedRef = useRef(translated);
  translatedRef.current = translated;
  const loaded = sugs.isSuccess;
  // On a new line: a line with no translation and no suggestion asks at once; any other waits for a click.
  useEffect(() => {
    if (!loaded) { setWant(null); return; }
    const held = queryClient.getQueryData<Suggestion[]>(["ollama", documentId])?.some((s) => s.line_number === lineNumber);
    setWant(!translatedRef.current && !held ? { line: lineNumber, reroll: false, n: 0 } : null);
  }, [queryClient, documentId, lineNumber, loaded]);
  const live = useOllamaStream(documentId, want, refresh);
  const stream = want?.line === lineNumber ? live : initial; // a render before the effect above catches up
  const state = cardState({ suggestion, translated, stream });
  const ask = (reroll: boolean) => setWant({ line: lineNumber, reroll, n: Date.now() });
  const liveText = stream.lines[lineNumber];
  const text = state === "saved" || state === "stale" ? suggestion?.text : liveText ?? undefined;
  const range = stream.first !== null && stream.last !== null ? lineRange(stream.first, stream.last) : null;
  return (
    <section className="mt-card" aria-label="Ollama">
      <header><h3>Ollama</h3><span className="muted mt-glyph">{state === "running" || state === "waiting" || state === "manual" ? "…" : ""}</span></header>
      {state === "running" && <p className="muted">{range ? `Translating lines ${range}…` : "Translating…"}</p>}
      {state === "waiting" && <p className="muted">Waiting for the night run's current chunk…</p>}
      {state === "manual" && <p className="muted">Waiting for another Ollama request…</p>}
      {suggestion && (state === "saved" || state === "stale") && (
        <p className="muted">{badge(suggestion, new Date())}
          {suggestion.stale && <> · <span className="badge warn">source changed</span></>}</p>
      )}
      {text && <p className="mt-text">{text}</p>}
      {stream.thinking && state === "running" && (
        <details><summary>Thinking</summary><p className="mt-text muted">{stream.thinking}</p></details>
      )}
      {state === "setup" && <p className="muted">{stream.message} <Link to="/settings/mt">Set up</Link></p>}
      {state === "error" && <p role="alert">{stream.message} <button onClick={() => ask(want?.reroll ?? false)}>Retry</button></p>}
      {sugs.error && <p className="error" role="alert">{sugs.error.message}</p>}
      <div className="mt-actions">
        {text && <button onClick={() => onUse(text)}>Use</button>}
        {suggestion && (state === "saved" || state === "stale") && (<>
          <button onClick={() => setReasoning(suggestion.chunk_id)}>Reasoning</button>
          <button onClick={() => ask(true)}>Reroll lines {lineRange(suggestion.first_line, suggestion.last_line)}</button>
        </>)}
        {state === "idle" && loaded && <button onClick={() => ask(false)}>Translate chunk</button>}
      </div>
      {reasoning !== null && <ReasoningDialog chunkId={reasoning} onClose={() => setReasoning(null)} />}
    </section>
  );
}
