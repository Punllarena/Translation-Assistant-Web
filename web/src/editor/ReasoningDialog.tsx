import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, call } from "../api/client";
import { lineRange, summary } from "./ollamaCardState";

const TABS = [
  { id: "reasoning", label: "Reasoning" },
  { id: "stats", label: "Stats" },
  { id: "prompt", label: "Prompt" },
] as const;
type Tab = (typeof TABS)[number]["id"];

const ms = (v: number | null) => (v === null ? "—" : `${(v / 1000).toFixed(1)} s`);

/** One Ollama chunk's reasoning, timings and prompt (GET /ollama/chunks/{id}). */
export default function ReasoningDialog({ chunkId, onClose }: { chunkId: number; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { const d = ref.current; if (d && !d.open) d.showModal(); }, []);
  const [tab, setTab] = useState<Tab>("reasoning");
  const chunk = useQuery({
    queryKey: ["ollama", "chunk", chunkId],
    queryFn: () => call(api.GET("/ollama/chunks/{chunk_id}", { params: { path: { chunk_id: chunkId } } })),
  });
  const c = chunk.data;
  return (
    <dialog ref={ref} onClose={onClose} aria-label="Ollama reasoning">
      <div className="dlg-head">
        <span className="label">Ollama</span>
        <h2>{c ? `Lines ${lineRange(c.first_line, c.last_line)}` : "Chunk"}</h2>
        {c && <p className="muted">{c.model}</p>}
      </div>
      <div className="tabs" role="tablist" aria-label="Chunk details">
        {TABS.map((t) => (
          <button key={t.id} type="button" role="tab" id={`ollama-tab-${t.id}`} aria-selected={tab === t.id}
            aria-controls={`ollama-panel-${t.id}`} onClick={() => setTab(t.id)}>{t.label}</button>
        ))}
      </div>
      <div className="dlg-body ollama-detail" role="tabpanel" id={`ollama-panel-${tab}`} aria-labelledby={`ollama-tab-${tab}`}>
        {chunk.isPending && <p className="muted">Loading…</p>}
        {chunk.error && <p className="error" role="alert">{chunk.error.message}</p>}
        {c && tab === "reasoning" && (<>
          {c.reasoning ? <p className="mt-text">{c.reasoning}</p> : <p className="muted">This model didn't reason.</p>}
          <p className="muted">{summary(c)}</p>
        </>)}
        {c && tab === "stats" && (
          <dl className="ollama-stats">
            <dt>Model</dt><dd>{c.model} ({c.preset})</dd>
            <dt>Lines</dt><dd>{lineRange(c.first_line, c.last_line)} ({c.asked} asked, {c.context_lines} of context)</dd>
            <dt>Tokens</dt><dd>{c.prompt_tokens.toLocaleString("en-US")} in / {c.output_tokens.toLocaleString("en-US")} out{c.clamped ? " (context clamped)" : ""}</dd>
            <dt>Load</dt><dd>{ms(c.load_ms)}</dd>
            <dt>Prompt</dt><dd>{ms(c.prompt_ms)}</dd>
            <dt>First token</dt><dd>{ms(c.first_token_ms)}</dd>
            <dt>Generation</dt><dd>{ms(c.eval_ms)}</dd>
            <dt>Total</dt><dd>{ms(c.total_ms)}</dd>
            <dt>Outcome</dt><dd>{c.ok ? "ok" : "failed"}{c.depth ? `, split ${c.depth}×` : ""} · {c.used_count} used, {c.edited_count} edited, {c.ignored_count} ignored</dd>
            {!c.ok && c.error && <><dt>Rejected</dt><dd>{c.error}</dd></>}
            <dt>Source</dt><dd>{c.source} · {new Date(c.created_at).toLocaleString()}</dd>
          </dl>
        )}
        {c && tab === "prompt" && (c.prompt ? <pre className="ollama-prompt mono">{c.prompt}</pre> : <p className="muted">No prompt kept.</p>)}
      </div>
      <div className="dlg-foot">
        <button type="button" onClick={() => ref.current?.close()}>Close</button>
      </div>
    </dialog>
  );
}
