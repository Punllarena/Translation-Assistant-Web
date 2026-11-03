import { useQuery } from "@tanstack/react-query";
import { useCallback, useMemo, useState } from "react";
import { Link } from "react-router";
import { api, call } from "../api/client";
import Entries from "./MtEntries";
import { apply, initial, type MtState } from "./mtEvents";
import { mergeEntries, toRow } from "./mtMerge";
import OllamaCard from "./OllamaCard";
import { useSse } from "./useSse";

const EVENTS = ["chunk", "thinking", "result", "analysis", "needs_setup", "error", "done"];
const LABELS: Record<string, string> = {
  deepl: "DeepL", libretranslate: "LibreTranslate", ollama: "Ollama", mecab: "MeCab", jparser: "JParser",
};
const RUNNING: MtState = { ...initial, status: "running" };

function useMtStream(backend: string, documentId: number, lineNumber: number) {
  const [attempt, setAttempt] = useState(0);
  const params = new URLSearchParams({ backend, document_id: String(documentId), line_number: String(lineNumber) });
  const state = useSse<MtState>({ url: `/api/mt/stream?${params}`, nonce: attempt, events: EVENTS, apply, initial, start: RUNNING });
  return { state, retry: useCallback(() => setAttempt((a) => a + 1), []) };
}

function glyphOf(state: MtState) {
  return state.status === "done" ? (state.cached ? "cached" : "✓") : state.status === "running" ? "…" : "";
}

function Status({ state, label }: { state: MtState; label?: string }) {
  const glyph = glyphOf(state);
  return (
    <span className="muted mt-glyph" role="status">
      {label && <span>{label} </span>}
      <span aria-hidden>{glyph}</span>
      {glyph && <span className="visually-hidden">{state.status === "done" ? (state.cached ? "Cached" : "Done") : "Translating"}</span>}
    </span>
  );
}

function Problems({ state, label, retry }: { state: MtState; label?: string; retry(): void }) {
  return (
    <>
      {state.status === "setup" && <p className="muted">{label && `${label}: `}{state.message} <Link to="/settings/mt">Set up</Link></p>}
      {state.status === "error" && <p role="alert">{label && `${label}: `}{state.message} <button onClick={retry}>Retry</button></p>}
    </>
  );
}

function Card({ name, label, documentId, lineNumber, onUse }: {
  name: string; label: string; documentId: number; lineNumber: number; onUse(text: string): void;
}) {
  const { state, retry } = useMtStream(name, documentId, lineNumber);
  return (
    <section className="mt-card" aria-label={label}>
      <header><h3>{label}</h3><Status state={state} /></header>
      {state.text && <p className="mt-text">{state.text}</p>}
      {state.thinking && <details><summary>Thinking</summary><p className="mt-text muted">{state.thinking}</p></details>}
      <Entries rows={state.entries.map(toRow)} />
      <Problems state={state} retry={retry} />
      {state.text && <button data-use onClick={() => onUse(state.text)}>Use</button>}
    </section>
  );
}

/** JParser and MeCab share a card: one row per word, MeCab's order and readings, JParser's meanings. */
function DictionaryCard({ documentId, lineNumber }: { documentId: number; lineNumber: number }) {
  const mecab = useMtStream("mecab", documentId, lineNumber);
  const jparser = useMtStream("jparser", documentId, lineNumber);
  const rows = useMemo(
    () => mergeEntries(mecab.state.entries, jparser.state.entries),
    [mecab.state.entries, jparser.state.entries],
  );
  return (
    <section className="mt-card" aria-label="Dictionary">
      <header>
        <h3>Dictionary</h3>
        <span className="mt-statuses">
          <Status state={jparser.state} label="JParser" />
          <Status state={mecab.state} label="MeCab" />
        </span>
      </header>
      <Entries rows={rows} />
      <Problems state={jparser.state} label="JParser" retry={jparser.retry} />
      <Problems state={mecab.state} label="MeCab" retry={mecab.retry} />
    </section>
  );
}

/** Machine translation cards for the active line, one SSE stream per enabled backend
 * (Ollama has its own card and endpoints: `translated` decides whether it asks unprompted). */
export default function MtPanels({ documentId, lineNumber, translated, onUse }: {
  documentId: number; lineNumber: number; translated: boolean; onUse(text: string): void;
}) {
  const backends = useQuery({ queryKey: ["mt", "backends"], queryFn: () => call(api.GET("/mt/backends")) });
  const enabled = backends.data?.enabled ?? [];
  if (!enabled.length) return null;
  const merged = enabled.includes("mecab") && enabled.includes("jparser");
  const first = enabled.find((n) => n === "mecab" || n === "jparser");
  return (
    <div className="mt-panels" aria-label="Machine translation">
      {enabled.map((name) => {
        if (name === "ollama") {
          return <OllamaCard key={name} documentId={documentId} lineNumber={lineNumber} translated={translated} onUse={onUse} />;
        }
        if (merged && (name === "mecab" || name === "jparser")) {
          return name === first ? <DictionaryCard key="dictionary" documentId={documentId} lineNumber={lineNumber} /> : null;
        }
        return <Card key={name} name={name} label={LABELS[name] ?? name} documentId={documentId} lineNumber={lineNumber} onUse={onUse} />;
      })}
    </div>
  );
}
