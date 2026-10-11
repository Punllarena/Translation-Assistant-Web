import type { EditorView } from "@codemirror/view";
import { useQuery } from "@tanstack/react-query";
import { useCallback, useMemo, useRef, type CSSProperties } from "react";
import { Link } from "react-router";
import { api, call, type Schemas } from "../api/client";
import CardList from "./CardList";
import CodeEditor from "./CodeEditor";
import { buildRows, firstContent, hasContent, progress } from "./rows";
import StatusBar from "./StatusBar";
import { useEditor } from "./useEditor";

type Data = Schemas["DocumentLines"];

export default function Editor({ id, data }: { id: number; data: Data; onProfile(id: number | null): void }) {
  const lines = data.lines;
  const startAt = useMemo(() => {
    const p = data.document.last_position;
    return lines[p] && hasContent(lines[p].raw_text) ? p : (firstContent(lines) ?? 0);
    // the opening position only
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const ed = useEditor(id, lines, startAt);
  const view = useRef<EditorView | null>(null);
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => call(api.GET("/settings")) });
  const fontPx = Number(settings.data?.editor_font_px ?? 18);
  const rows = useMemo(() => buildRows(lines, []), [lines]);
  const stats = useMemo(() => progress(lines, ed.texts), [lines, ed.texts]);
  const onReady = useCallback((v: EditorView | null) => { view.current = v; }, []);
  const current = lines[ed.active];
  // Every hook stays above this early return; later tasks add theirs here too and read
  // `current?.` (it is undefined for a chapter with no lines).

  if (!rows.some((r) => r.kind === "line")) {
    return <main><p>This chapter has no source text yet. <Link to="/">Back to the library</Link></p></main>;
  }
  const n = current.line_number;
  const editor = (
    <CodeEditor key={n} initial={ed.texts[n] ?? ""} label="Translation"
      onChange={(t) => ed.setText(n, t)} onBlur={() => void ed.store.flush()} onReady={onReady} />
  );
  return (
    <div className="editor-page" style={{ "--editor-font": `${fontPx}px` } as CSSProperties}>
      <StatusBar title={data.document.title} line={n + 1} total={lines.length}
        percent={stats.percent} words={stats.words}
        phrase={ed.parse >= 0 ? `Phrase ${ed.parse + 1}/${current.sentences.length}` : null}
        save={ed.save} onRetry={() => void ed.store.flush()} />
      <div className="editor">
        <CardList rows={rows} active={ed.active} parse={ed.parse} texts={ed.texts}
          onActivate={ed.activate} editor={editor} />
      </div>
    </div>
  );
}
