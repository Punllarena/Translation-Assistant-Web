import type { EditorView } from "@codemirror/view";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { Link } from "react-router";
import { api, call, type Schemas } from "../api/client";
import CardList from "./CardList";
import CodeEditor, { insertAtCursor, setMarks } from "./CodeEditor";
import FindBar from "./FindBar";
import { firstFrom, findHits, wrapStep } from "./find";
import { PUNCTUATIONS } from "./keymap";
import { advanceParse, retreatParse } from "./parse";
import { buildRows, firstContent, firstUntranslated, hasContent, lineAtOrAfter, nextContent, prevContent, progress } from "./rows";
import StatusBar from "./StatusBar";
import { useEditor } from "./useEditor";
import { useBindings, useEditorKeys } from "./useEditorKeys";

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
  const queryClient = useQueryClient();
  const setFont = (px: number) => {
    const size = Math.max(12, Math.min(32, px));
    queryClient.setQueryData(["settings"], { ...settings.data, editor_font_px: size });
    void call(api.PUT("/settings", { body: { editor_font_px: size } })).catch(() => {});
  };
  const [find, setFind] = useState<{ open: number; needle: string; at: number }>({ open: 0, needle: "", at: -1 });
  const hits = useMemo(
    () => findHits(rows.flatMap((r) => r.kind === "line"
      ? [{ index: r.index, source: r.line.display_text, translation: ed.texts[r.line.line_number] ?? "" }]
      : []), find.needle),
    [rows, ed.texts, find.needle],
  );
  const at = find.at < hits.length ? find.at : -1;
  const hit = find.open && at >= 0 ? hits[at] : null;
  const step = (dir: 1 | -1) => {
    const next = at < 0 && dir === 1 ? firstFrom(hits, ed.active) : wrapStep(at, hits.length, dir);
    setFind((f) => ({ ...f, at: next }));
    if (hits[next]) ed.activate(hits[next].index);
  };
  useEffect(() => {
    const marks = hit && hit.index === ed.active && hit.field === "translation"
      ? [{ from: hit.from, to: hit.to, cls: "find-current" }] : [];
    view.current?.dispatch({ effects: setMarks.of(marks) });
  }, [hit, ed.active]);
  const run = (action: string) => {
    const at = ed.active;
    if (!lines[at]) return;
    switch (action) {
      case "save_next":
        void ed.store.flush();
        ed.activate(nextContent(lines, at));
        break;
      case "next":
      case "next_alt":
        ed.activate(nextContent(lines, at));
        break;
      case "prev":
      case "prev_alt":
        ed.activate(prevContent(lines, at));
        break;
      case "first":
        ed.activate(firstContent(lines));
        break;
      case "next_untranslated":
        // desktop: only from a line that already has a translation
        if (ed.texts[lines[at].line_number]) ed.activate(firstUntranslated(lines, ed.texts));
        break;
      case "parse_next":
        ed.setParse((p) => advanceParse(p, lines[at].sentences.length));
        break;
      case "parse_prev":
        ed.setParse((p) => retreatParse(p, lines[at].replaced));
        break;
      case "go_to_line": {
        const answer = window.prompt(`Go to line (1\u2013${lines.length})`);
        const k = Number(answer);
        if (answer && Number.isInteger(k)) ed.activate(lineAtOrAfter(lines, k));
        break;
      }
      case "font_larger":
        setFont(fontPx + 1);
        break;
      case "font_smaller":
        setFont(fontPx - 1);
        break;
      case "find":
        setFind((f) => ({ ...f, open: f.open + 1 }));
        break;
      default:
        if (action.startsWith("punct_")) insertAtCursor(view.current, PUNCTUATIONS[Number(action.slice(6))], 1);
    }
  };
  useEditorKeys(useBindings(), run);
  // Every hook stays above this early return; later tasks add theirs here too and read
  // `current?.` (it is undefined for a chapter with no lines).

  if (!rows.some((r) => r.kind === "line")) {
    return <main><p>This chapter has no source text yet. <Link to="/">Back to the library</Link></p></main>;
  }
  const n = current.line_number;
  const editor = (
    <CodeEditor key={n} value={ed.texts[n] ?? ""} label="Translation"
      onChange={(t) => ed.setText(n, t)} onBlur={() => void ed.store.flush()} onReady={onReady} autoFocus={find.open === 0} />
  );
  return (
    <div className="editor-page" style={{ "--editor-font": `${fontPx}px` } as CSSProperties}>
      <StatusBar title={data.document.title} line={n + 1} total={lines.length}
        percent={stats.percent} words={stats.words}
        phrase={ed.parse >= 0 ? `Phrase ${ed.parse + 1}/${current.sentences.length}` : null}
        save={ed.save} onRetry={() => void ed.store.flush()} />
      {find.open > 0 && (
        <FindBar key={find.open} needle={find.needle} position={at} total={hits.length}
          onNeedle={(needle) => setFind((f) => ({ ...f, needle, at: -1 }))} onStep={step}
          onClose={() => { setFind((f) => ({ ...f, open: 0, at: -1 })); view.current?.focus(); }} />
      )}
      <div className="editor">
        <CardList rows={rows} active={ed.active} parse={ed.parse} texts={ed.texts}
          onActivate={ed.activate} editor={editor} highlight={hit} />
      </div>
    </div>
  );
}
