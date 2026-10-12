import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";
import { api, call } from "../api/client";
import { apply, initial, type Entry, type MtState } from "./mtEvents";

const EVENTS = ["chunk", "thinking", "result", "analysis", "needs_setup", "error", "done"];
const LABELS: Record<string, string> = {
  deepl: "DeepL", libretranslate: "LibreTranslate", ollama: "Ollama", mecab: "MeCab", jparser: "JParser",
};
const TERMINAL = new Set(["needs_setup", "error", "done"]);

function useMtStream(backend: string, documentId: number, lineNumber: number, profileId: number | null) {
  const [state, setState] = useState<MtState>(initial);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    setState({ ...initial, status: "running" });
    let es: EventSource | null = null;
    const timer = setTimeout(() => {
      const params = new URLSearchParams({ backend, document_id: String(documentId), line_number: String(lineNumber) });
      if (profileId != null) params.set("profile_id", String(profileId));
      const source = new EventSource(`/api/mt/stream?${params}`);
      es = source;
      let heard = false;
      for (const type of EVENTS) {
        source.addEventListener(type, (e) => {
          heard = true;
          let data: unknown = {};
          try { data = JSON.parse((e as MessageEvent).data); } catch { /* keep {} */ }
          setState((s) => apply(s, type, data));
          if (TERMINAL.has(type)) source.close();
        });
      }
      source.onerror = () => {
        if (!heard) setState((s) => apply(s, "error", { message: "Connection failed" }));
        source.close();
      };
    }, 300);
    return () => { clearTimeout(timer); es?.close(); };
  }, [backend, documentId, lineNumber, profileId, attempt]);
  return { state, retry: useCallback(() => setAttempt((a) => a + 1), []) };
}

function EntryRow({ e }: { e: Entry }) {
  const lemma = [e.lemma, e.base_form].filter((x, i, a) => x && a.indexOf(x) === i && x !== e.surface).join(" / ");
  return (
    <li className={e.matched === false ? "muted" : undefined}>
      <b>{e.surface}</b>
      {e.reading ? ` [${e.reading}]` : ""}
      {lemma ? ` (${lemma})` : ""}
      {e.pos ? ` ‹${e.pos}›` : ""}
      {e.tense ? ` ${e.tense}` : ""}
      {e.gloss ? ` — ${e.gloss}` : ""}
    </li>
  );
}

function Card({ name, label, documentId, lineNumber, profileId, onUse }: {
  name: string; label: string; documentId: number; lineNumber: number; profileId: number | null; onUse(text: string): void;
}) {
  const { state, retry } = useMtStream(name, documentId, lineNumber, profileId);
  const glyph = state.status === "done" ? (state.cached ? "cached" : "✓") : state.status === "running" ? "…" : "";
  return (
    <section className="mt-card" aria-label={label}>
      <header><h3>{label}</h3><span className="muted mt-glyph">{glyph}</span></header>
      {state.text && <p className="mt-text">{state.text}</p>}
      {state.thinking && <details><summary>Thinking</summary><p className="mt-text muted">{state.thinking}</p></details>}
      {state.entries.length > 0 && <ul className="mt-entries">{state.entries.map((e, i) => <EntryRow key={i} e={e} />)}</ul>}
      {state.status === "setup" && <p className="muted">{state.message} <Link to="/settings/mt">Set up</Link></p>}
      {state.status === "error" && <p role="alert">{state.message} <button onClick={retry}>Retry</button></p>}
      {state.text && <button onClick={() => onUse(state.text)}>Use</button>}
    </section>
  );
}

/** Machine translation cards for the active line, one SSE stream per enabled backend. */
export default function MtPanels({ documentId, lineNumber, profileId, onUse }: {
  documentId: number; lineNumber: number; profileId: number | null; onUse(text: string): void;
}) {
  const backends = useQuery({ queryKey: ["mt", "backends"], queryFn: () => call(api.GET("/mt/backends")) });
  const enabled = backends.data?.enabled ?? [];
  if (!enabled.length) return null;
  return (
    <div className="mt-panels" aria-label="Machine translation">
      {enabled.map((name) => (
        <Card key={name} name={name} label={LABELS[name] ?? name}
          documentId={documentId} lineNumber={lineNumber} profileId={profileId} onUse={onUse} />
      ))}
    </div>
  );
}
