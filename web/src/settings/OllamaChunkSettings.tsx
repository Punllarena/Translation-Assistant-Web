import { useEffect, useState } from "react";
import { PRESETS, type PresetKey } from "./ollamaPresets";

type Props = {
  settings: Record<string, unknown>;
  /** The Ollama entry's message from /mt/backends, if any. */
  message?: string;
  save: (body: Record<string, unknown>) => void;
  clear: (key: string) => void;
};

const whole = (v: unknown, lo: number, hi: number) => (typeof v === "number" && Number.isInteger(v) && v >= lo && v <= hi ? v : null);

/** Ollama background translation: chunk size, context lines, presets and CPU threads. */
export default function OllamaChunkSettings({ settings: s, message, save, clear }: Props) {
  const stored = s.ollama_preset;
  const preset: PresetKey = stored === "medium" || stored === "large" || stored === "custom" ? stored : "small";
  const known = preset !== "custom";
  const chunk = known ? PRESETS[preset].chunk : whole(s.ollama_chunk_lines, 0, 500) ?? PRESETS.small.chunk;
  const context = known ? PRESETS[preset].context : whole(s.ollama_context_lines, 0, 50) ?? PRESETS.small.context;
  const threads = whole(s.ollama_num_thread, 1, 64);

  const [threadText, setThreadText] = useState(threads === null ? "" : String(threads));
  useEffect(() => { setThreadText(threads === null ? "" : String(threads)); }, [threads]);

  const pick = (k: PresetKey) => {
    if (k === "custom") save({ ollama_preset: "custom", ollama_chunk_lines: chunk, ollama_context_lines: context });
    else save({ ollama_preset: k, ollama_chunk_lines: PRESETS[k].chunk, ollama_context_lines: PRESETS[k].context });
  };
  const edit = (c: number, x: number) => save({ ollama_preset: "custom", ollama_chunk_lines: c, ollama_context_lines: x });
  const saveThreads = () => {
    const t = threadText.trim();
    if (t === "") { if (threads !== null) clear("ollama_num_thread"); return; }
    const n = Number(t);
    if (Number.isInteger(n) && n >= 1 && n <= 64 && n !== threads) save({ ollama_num_thread: n });
  };
  const wholeChapter = chunk === 0;

  return (
    <div className="stack" aria-label="Ollama chunking">
      <h3>Background translation</h3>
      <label className="field"><span>Preset</span>
        <select aria-label="Ollama preset" value={preset}
          onChange={(e) => pick(e.target.value as PresetKey)}>
          {(Object.keys(PRESETS) as PresetKey[]).map((k) => <option key={k} value={k}>{PRESETS[k].label}</option>)}
        </select>
      </label>
      <div className="row-fields">
        <label className="field"><span>Chunk size (lines)</span>
          <input type="number" min={1} max={500} aria-label="Ollama chunk size" disabled={wholeChapter}
            value={wholeChapter ? "" : chunk}
            onChange={(e) => { const n = Number(e.target.value); if (Number.isInteger(n) && n >= 1 && n <= 500) edit(n, context); }} /></label>
        <label className="check"><input type="checkbox" aria-label="Whole chapter" checked={wholeChapter}
          onChange={(e) => edit(e.target.checked ? 0 : PRESETS.small.chunk, context)} />Whole chapter</label>
        <label className="field"><span>Context lines</span>
          <input type="number" min={0} max={50} aria-label="Ollama context lines" value={context}
            onChange={(e) => { const n = Number(e.target.value); if (e.target.value !== "" && Number.isInteger(n) && n >= 0 && n <= 50) edit(chunk, n); }} /></label>
      </div>
      <p className="hint">Context lines are earlier lines sent along for reference and not translated again.</p>
      <details>
        <summary>Advanced</summary>
        <label className="field"><span>CPU threads (empty = Ollama default)</span>
          <input type="number" min={1} max={64} aria-label="Ollama CPU threads" value={threadText}
            onChange={(e) => setThreadText(e.target.value)} onBlur={saveThreads} /></label>
      </details>
      {message?.includes("private or local address") && (
        <p className="hint" role="note">{message} An admin can allow private addresses under Admin → Server settings.</p>
      )}
    </div>
  );
}
