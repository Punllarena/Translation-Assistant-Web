import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { api, call } from "../api/client";
import { CardAction, CardReady, CardStatus } from "./CardParts";
import { friendlyError } from "./cardCopy";
import { apply, badge, cardState, coversLine, initial, lineRange, type StreamState, type Suggestion } from "./ollamaCardState";
import ReasoningDialog from "./ReasoningDialog";
import { useSse } from "./useSse";

const EVENTS = ["plan", "waiting", "thinking", "line", "saved", "needs_setup", "error", "done"];
const RUNNING: StreamState = { ...initial, status: "running" };

/** A request for the chunk holding `line`; `n` makes a repeat (Retry, a second click) a new one. */
type Want = { line: number; reroll: boolean; n: number };

const streamUrl = (documentId: number, want: Want | null) => want && `/api/documents/${documentId}/ollama/stream?${
  new URLSearchParams({ line_number: String(want.line), reroll: String(want.reroll) })}`;

/** The Ollama card: the line's saved suggestion (Use / Reasoning / Re-translate), or by-hand
 * translation of the chunk the line belongs to, streamed line by line. */
export default function OllamaCard({ documentId, lineNumber, translated, onUse, slot, bindings }: {
  documentId: number; lineNumber: number; translated: boolean; onUse(text: string): void;
  slot?: number; bindings: Record<string, string>;
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
  const [reroll, setReroll] = useState<Want | null>(null);
  const [reasoning, setReasoning] = useState<number | null>(null);
  const translatedRef = useRef(translated);
  translatedRef.current = translated;
  const loaded = sugs.data !== undefined; // a failed background refetch keeps the data, and the stream
  // On a new line: a line with no translation and no suggestion asks at once; any other waits for a click.
  useEffect(() => {
    if (!loaded) { setWant(null); return; }
    const held = queryClient.getQueryData<Suggestion[]>(["ollama", documentId])?.some((s) => s.line_number === lineNumber);
    setWant(!translatedRef.current && !held ? { line: lineNumber, reroll: false, n: 0 } : null);
  }, [queryClient, documentId, lineNumber, loaded]);
  // Closing the stream (a new want, the card unmounting) leaves the chunk running on the server;
  // asking again for a line of it follows it. The server sends saved, then done.
  const live = useSse<StreamState>({
    url: streamUrl(documentId, want), nonce: want, events: EVENTS, apply, initial, start: RUNNING,
    onEvent: (type) => { if (type === "done") refresh(); },
  });
  // A reroll has its own stream, kept while the card moves to another line: the chunk is
  // server-owned, so switching lines must neither cancel it nor leave this document's saved
  // suggestions stale when it finishes.
  const rerollLive = useSse<StreamState>({
    url: streamUrl(documentId, reroll), nonce: reroll, events: EVENTS, apply, initial, start: RUNNING,
    onEvent: (type) => { if (type === "done") { refresh(); setReroll(null); } },
  });
  const rerolling = coversLine(reroll, rerollLive, lineNumber);
  const stream = rerolling ? rerollLive : want?.line === lineNumber ? live : initial; // a render before the effect above catches up
  const state = cardState({ suggestion, translated, stream });
  const ask = (wantsReroll: boolean) => {
    const next = { line: lineNumber, reroll: wantsReroll, n: Date.now() };
    if (wantsReroll) { setReroll(next); setWant(null); }
    else setWant(next);
  };
  const liveText = stream.lines[lineNumber];
  const text = state === "saved" || state === "stale" ? suggestion?.text : liveText ?? undefined;
  const range = stream.first !== null && stream.last !== null ? lineRange(stream.first, stream.last) : null;
  const busy = state === "running" || state === "waiting" || state === "manual";
  const aid = state === "error" || state === "setup" || sugs.error ? "error"
    : busy || !loaded ? "busy" : state === "idle" ? "empty" : "ready";
  return (
    <section className={`mt-card state-${aid}`} aria-label="Ollama">
      <header>
        <h3>Ollama</h3>
        <span className="card-meta">
          {aid === "ready" && <CardReady />}
          {aid === "ready" && slot !== undefined && <span className="use-key" aria-hidden="true">{bindings[`use_${slot}`]}</span>}
          {aid === "empty" && <span className="card-note muted">No match</span>}
          {/* One state word here; the body says what it means. */}
          {aid === "busy" && (
            <span className="badge" role="status">
              {state === "running" ? "Running" : state === "waiting" ? "Waiting" : "Queued"}
            </span>
          )}
        </span>
      </header>
      {state === "running" && <p className="muted">{range ? `Translating lines ${range}…` : "Translating…"}</p>}
      {state === "waiting" && <p className="muted">The night run is translating this passage; yours starts when it finishes.</p>}
      {state === "manual" && <p className="muted">Another Ollama request is running; yours follows.</p>}
      {suggestion && (state === "saved" || state === "stale") && (
        <p className="muted">{badge(suggestion, new Date())}
          {suggestion.stale && <> · <span className="badge warn">source changed</span></>}</p>
      )}
      {suggestion?.stale && (state === "saved" || state === "stale") && (
        <p className="card-note muted">The Japanese line changed after this draft.</p>
      )}
      {text && <p className="mt-text">{text}</p>}
      {stream.thinking && state === "running" && (
        <details><summary>Thinking</summary><p className="mt-text muted">{stream.thinking}</p></details>
      )}
      {state === "setup" && (
        <CardStatus kind="info">{stream.message} <Link to="/settings/mt">Set up</Link></CardStatus>
      )}
      {(state === "error" || sugs.error) && (
        <CardStatus kind="error">
          {friendlyError(state === "error" ? stream.message : sugs.error?.message ?? "", "Ollama")}
        </CardStatus>
      )}
      <div className="mt-actions">
        {text && (
          <CardAction tone="use" slot={slot} onClick={() => onUse(text)}
            label={slot !== undefined ? `Use Ollama, ${bindings[`use_${slot}`]}` : "Use Ollama"}>Use</CardAction>
        )}
        {state === "error" && <CardAction onClick={() => ask(stream === rerollLive)}>Retry</CardAction>}
        {suggestion && (state === "saved" || state === "stale") && (<>
          <CardAction onClick={() => setReasoning(suggestion.chunk_id)}>Reasoning</CardAction>
          <CardAction onClick={() => ask(true)} title="Replaces the suggestions for these lines">
            Re-translate lines {lineRange(suggestion.first_line, suggestion.last_line)}
          </CardAction>
        </>)}
        {state === "idle" && loaded && <CardAction onClick={() => ask(false)}>Translate this passage</CardAction>}
      </div>
      {reasoning !== null && <ReasoningDialog chunkId={reasoning} onClose={() => setReasoning(null)} />}
    </section>
  );
}
