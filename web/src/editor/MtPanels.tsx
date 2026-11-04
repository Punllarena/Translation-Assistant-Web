import { useQuery } from "@tanstack/react-query";
import { useCallback, useMemo, useState } from "react";
import { Link } from "react-router";
import { api, call } from "../api/client";
import { CardAction, CardReady, CardStatus } from "./CardParts";
import { friendlyError } from "./cardCopy";
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

/** How the card ranks in the aid column: what can be used, what is working, what needs
 *  attention, then what has nothing to say. */
type Aid = "ready" | "busy" | "empty" | "error";

function aidOf(state: MtState, has: boolean): Aid {
  if (state.status === "error" || state.status === "setup") return "error";
  if (state.status === "done") return has ? "ready" : "empty";
  return "busy";
}

function Status({ state, label }: { state: MtState; label?: string }) {
  if (state.status === "running") return <CardStatus kind="busy">{label ? `${label} translating` : "Translating"}</CardStatus>;
  if (state.status !== "done") return null;
  return (
    <span className="muted mt-glyph">
      {label && <span>{label} </span>}
      <span aria-hidden>{state.cached ? "cached" : "✓"}</span>
      <span className="visually-hidden">{state.cached ? "Cached" : "Done"}</span>
    </span>
  );
}

type Problem = { state: MtState; label?: string; retry(): void };

/** One alert per card, even when both halves of the Dictionary card fail. */
function Problems({ items }: { items: Problem[] }) {
  const setup = items.filter((p) => p.state.status === "setup");
  if (setup.length) {
    return (
      <CardStatus kind="info">
        {setup.map((p, i) => (
          <span key={p.label ?? i}>{i > 0 && " "}{p.label && `${p.label}: `}{p.state.message}</span>
        ))}{" "}<Link to="/settings/mt">Set up</Link>
      </CardStatus>
    );
  }
  const errors = items.filter((p) => p.state.status === "error");
  if (!errors.length) return null;
  return (
    <>
      <CardStatus kind="error">
        {errors.map((p, i) => (
          <span key={p.label ?? i}>{i > 0 && " "}{p.label && `${p.label}: `}{friendlyError(p.state.message, p.label)}</span>
        ))}
      </CardStatus>
      <div className="mt-actions">
        {errors.map((p) => (
          <CardAction key={p.label ?? "retry"} onClick={p.retry}>
            {errors.length > 1 && p.label ? `Retry ${p.label}` : "Retry"}
          </CardAction>
        ))}
      </div>
    </>
  );
}

function Card({ name, label, documentId, lineNumber, onUse, slot, bindings }: {
  name: string; label: string; documentId: number; lineNumber: number; onUse(text: string): void;
  slot?: number; bindings: Record<string, string>;
}) {
  const { state, retry } = useMtStream(name, documentId, lineNumber);
  const aid = aidOf(state, Boolean(state.text));
  return (
    <section className={`mt-card state-${aid}`} aria-label={label}>
      <header>
        <h3>{label}</h3>
        <span className="card-meta">
          {aid === "ready" && <CardReady />}
          {aid === "ready" && state.cached && <span className="card-note muted">cached</span>}
          {aid === "ready" && slot !== undefined && <span className="use-key" aria-hidden="true">{bindings[`use_${slot}`]}</span>}
          {aid !== "ready" && (aid === "empty"
            ? <span className="card-note muted">No match</span>
            : <Status state={state} />)}
        </span>
      </header>
      {state.text && <p className="mt-text">{state.text}</p>}
      {state.thinking && <details><summary>Thinking</summary><p className="mt-text muted">{state.thinking}</p></details>}
      <Entries rows={state.entries.map(toRow)} />
      <Problems items={[{ state, label: undefined, retry }]} />
      {/* A stream still sending text offers no Use: half a translation is not one. */}
      {state.status === "done" && state.text && (
        <div className="mt-actions">
          <CardAction tone="use" slot={slot} onClick={() => onUse(state.text)}
            label={slot !== undefined ? `Use ${label}, ${bindings[`use_${slot}`]}` : `Use ${label}`}>Use</CardAction>
        </div>
      )}
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
  const broken = [jparser.state, mecab.state].some((s) => s.status === "error" || s.status === "setup");
  const working = jparser.state.status === "running" || mecab.state.status === "running";
  const aid: Aid = rows.length ? "ready" : broken ? "error" : working ? "busy" : "empty";
  return (
    <section className={`mt-card state-${aid}`} aria-label="Dictionary">
      <header>
        <h3>Dictionary</h3>
        <span className="mt-statuses">
          {aid === "ready" && <CardReady />}
          {aid === "empty" ? <span className="card-note muted">No match</span> : (
            <>
              <Status state={jparser.state} label="JParser" />
              <Status state={mecab.state} label="MeCab" />
            </>
          )}
        </span>
      </header>
      <Entries rows={rows} />
      <Problems items={[
        { state: jparser.state, label: "JParser", retry: jparser.retry },
        { state: mecab.state, label: "MeCab", retry: mecab.retry },
      ]} />
    </section>
  );
}

/** Machine translation cards for the active line, one SSE stream per enabled backend
 * (Ollama has its own card and endpoints: `translated` decides whether it asks unprompted). */
export default function MtPanels({ documentId, lineNumber, translated, onUse, slots, bindings }: {
  documentId: number; lineNumber: number; translated: boolean; onUse(text: string): void;
  slots: { backends: Record<string, number> }; bindings: Record<string, string>;
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
          return (
            <OllamaCard key={name} documentId={documentId} lineNumber={lineNumber} translated={translated} onUse={onUse}
              slot={slots.backends[name]} bindings={bindings} />
          );
        }
        if (merged && (name === "mecab" || name === "jparser")) {
          return name === first ? <DictionaryCard key="dictionary" documentId={documentId} lineNumber={lineNumber} /> : null;
        }
        return (
          <Card key={name} name={name} label={LABELS[name] ?? name} documentId={documentId} lineNumber={lineNumber}
            onUse={onUse} slot={slots.backends[name]} bindings={bindings} />
        );
      })}
    </div>
  );
}
