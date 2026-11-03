import { useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { Link } from "react-router";
import { api, call } from "../api/client";
import { apply, initial, type Entry, type MtState } from "./mtEvents";
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

const POS_WORDS: Record<string, string> = {
  n: "noun", pn: "pronoun", conj: "conjunction", pref: "prefix", prt: "particle", suf: "suffix",
  v1: "verb (ichidan)", v5: "verb (godan)", vt: "transitive", vi: "intransitive", vs: "suru verb",
  "adj-i": "i-adjective", "adj-na": "na-adjective", adv: "adverb", int: "interjection", ctr: "counter", exp: "expression",
};
const KANA_ONLY = /^[぀-ヿー]+$/;

function EntryRow({ e }: { e: Entry }) {
  const lemma = [e.lemma, e.base_form].filter((x, i, a) => x && a.indexOf(x) === i && x !== e.surface).join(" / ");
  const reading = e.reading && !KANA_ONLY.test(e.surface) ? e.reading : "";
  const pos = e.pos?.split(",").map((t) => POS_WORDS[t.trim()] ?? t.trim()).join(", ");
  const noMatch = e.matched === false && !e.gloss;
  return (
    <li className={e.matched === false ? "muted" : undefined}>
      <span className="mt-surface" lang="ja">{e.surface}</span>
      {reading && <span className="mt-reading" lang="ja"><span aria-hidden>【</span>{reading}<span aria-hidden>】</span></span>}
      {lemma && <span className="mt-lemma" lang="ja"><span aria-hidden>← </span>{lemma}</span>}
      {(pos || e.tense || e.gloss || noMatch) && (
        <span className="mt-gloss">
          {pos && <span className="mt-pos" title={e.pos} lang={/[^\u0000-\u007f]/.test(pos) ? "ja" : undefined}>{pos}</span>}
          {e.tense && <span className="mt-pos">{e.tense}</span>}
          {noMatch ? <span className="mt-nomatch">no entry</span> : e.gloss}
        </span>
      )}
    </li>
  );
}

function Card({ name, label, documentId, lineNumber, onUse }: {
  name: string; label: string; documentId: number; lineNumber: number; onUse(text: string): void;
}) {
  const { state, retry } = useMtStream(name, documentId, lineNumber);
  const glyph = state.status === "done" ? (state.cached ? "cached" : "✓") : state.status === "running" ? "…" : "";
  return (
    <section className="mt-card" aria-label={label}>
      <header><h3>{label}</h3><span className="muted mt-glyph" role="status">
        <span aria-hidden>{glyph}</span>
        {glyph && <span className="visually-hidden">{state.status === "done" ? (state.cached ? "Cached" : "Done") : "Translating"}</span>}
      </span></header>
      {state.text && <p className="mt-text">{state.text}</p>}
      {state.thinking && <details><summary>Thinking</summary><p className="mt-text muted">{state.thinking}</p></details>}
      {state.entries.length > 0 && <ul className="mt-entries">{state.entries.map((e, i) => <EntryRow key={i} e={e} />)}</ul>}
      {state.status === "setup" && <p className="muted">{state.message} <Link to="/settings/mt">Set up</Link></p>}
      {state.status === "error" && <p role="alert">{state.message} <button onClick={retry}>Retry</button></p>}
      {state.text && <button data-use onClick={() => onUse(state.text)}>Use</button>}
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
  return (
    <div className="mt-panels" aria-label="Machine translation">
      {enabled.map((name) => name === "ollama" ? (
        <OllamaCard key={name} documentId={documentId} lineNumber={lineNumber} translated={translated} onUse={onUse} />
      ) : (
        <Card key={name} name={name} label={LABELS[name] ?? name}
          documentId={documentId} lineNumber={lineNumber} onUse={onUse} />
      ))}
    </div>
  );
}
