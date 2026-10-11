import { EditorView } from "@codemirror/view";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { api, ApiError, call, type Schemas } from "../api/client";
import { invalidateLibrary } from "../library/queries";
import CodeEditor, { setMarks } from "./CodeEditor";
import { cutsFromText, firstTextDifference, insertMarker, SPLIT_MARKER } from "./cuts";
import FindBar from "./FindBar";
import { findIn, wrapStep } from "./find";
import { bindingOf } from "./keymap";
import { sourceText } from "./rows";
import { useBindings } from "./useEditorKeys";

/** Edit Source and Split (desktop _EditSourceDialog / _SplitChapterDialog): one line per
 *  line, $ marks a continuation. Split: place markers where new chapters start. */
export default function SourcePage({ mode }: { mode: "edit" | "split" }) {
  const id = Number(useParams().id);
  const mountedAt = useRef(Date.now());
  // Always the server's current lines: this text is what gets saved back.
  const doc = useQuery({
    queryKey: ["document", id, "lines", null],
    queryFn: () => call(api.GET("/documents/{document_id}/lines", { params: { path: { document_id: id } } })),
    gcTime: 0,
    refetchOnMount: "always",
  });
  if (doc.isError) return <main><p className="error" role="alert">{doc.error.message}</p><Link to="/">Back to the library</Link></main>;
  if (doc.isPending || doc.dataUpdatedAt < mountedAt.current) return <main><p className="muted">Loading…</p></main>;
  return <SourceBody key={id} id={id} mode={mode} data={doc.data} />;
}

function SourceBody({ id, mode, data }: { id: number; mode: "edit" | "split"; data: Schemas["DocumentLines"] }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const view = useRef<EditorView | null>(null);
  const original = useMemo(() => sourceText(data.lines), [data.lines]);
  const [text, setText] = useState(original);
  const [problem, setProblem] = useState<string | null>(null);
  const [find, setFind] = useState({ open: 0, needle: "", at: -1 });
  const bindings = useBindings();
  const dirty = text !== original;
  const hits = useMemo(() => findIn(text, find.needle), [text, find.needle]);
  const onReady = useCallback((v: EditorView | null) => { view.current = v; }, []);

  const done = async (to: number) => {
    await queryClient.invalidateQueries({ queryKey: ["document", id] });
    await invalidateLibrary(queryClient);
    navigate(`/documents/${to}`);
  };
  const save = useMutation({
    mutationFn: (force: boolean) =>
      call(api.PUT("/documents/{document_id}/source", { params: { path: { document_id: id } }, body: { text, force } })),
    onSuccess: () => { sent.current = true; return done(id); },
    onError: (e, force) => {
      // Only the first (non-forced) attempt asks; a forced retry that fails shows its error.
      if (e instanceof ApiError && e.status === 409 && !force
          && window.confirm(`${e.message}. Translations will then sit next to different source lines. Save anyway?`)) {
        save.mutate(true);
      }
    },
  });
  const split = useMutation({
    mutationFn: (cuts: { start: number; title: string }[]) =>
      call(api.POST("/documents/{document_id}/split", { params: { path: { document_id: id } }, body: { cuts } })),
    onSuccess: (docs) => { sent.current = true; return done(docs[0]?.id ?? id); },
  });
  const sent = useRef(false); // saved or split: nothing left to warn about

  // Unsaved edits are lost on reload or tab close.
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => { if (!sent.current) e.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (bindingOf(e) !== bindings.find) return;
      e.preventDefault();
      setFind((f) => ({ ...f, open: f.open + 1 }));
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [bindings.find]);

  const clearMarks = () => view.current?.dispatch({ effects: setMarks.of([]) });
  const at = find.at < hits.length ? find.at : -1;
  const step = (dir: 1 | -1) => {
    const next = wrapStep(at, hits.length, dir);
    setFind((f) => ({ ...f, at: next }));
    const range = hits[next];
    view.current?.dispatch({
      effects: range
        ? [setMarks.of([{ from: range[0], to: range[1], cls: "find-current" }]), EditorView.scrollIntoView(range[0], { y: "center" })]
        : [setMarks.of([])],
    });
  };
  const leave = (e: React.MouseEvent) => {
    if (dirty && !window.confirm("Discard your unsaved changes?")) e.preventDefault();
  };

  const error = problem
    ?? (save.isError && !(save.error instanceof ApiError && save.error.status === 409 && !save.variables) ? save.error.message : null)
    ?? split.error?.message;
  return (
    <main>
      <p><Link to={`/documents/${id}`} onClick={leave}>← Back to the editor</Link></p>
      <h1>{mode === "edit" ? "Edit source" : "Split chapter"} — {data.document.title}</h1>
      <p className="muted">
        {mode === "edit"
          ? "One line per paragraph; a line starting with $ continues the previous one. Translations stay with their line position."
          : `Put the cursor on the first line of each new chapter and press "Insert split here"; type its title after ${SPLIT_MARKER}. Text edits here are ignored — use Edit Source to change wording.`}
      </p>
      {find.open > 0 && (
        <FindBar key={find.open} needle={find.needle} position={at} total={hits.length}
          onNeedle={(needle) => { setFind((f) => ({ ...f, needle, at: -1 })); clearMarks(); }} onStep={step}
          onClose={() => { setFind((f) => ({ ...f, open: 0, at: -1 })); clearMarks(); view.current?.focus(); }} />
      )}
      <div className="source-editor">
        <CodeEditor value={text} label="Source text" onChange={(t) => { setText(t); setProblem(null); }} onReady={onReady} />
      </div>
      <div className="toolbar">
        {mode === "edit" ? (
          <button onClick={() => save.mutate(false)} disabled={save.isPending}>Save</button>
        ) : (
          <>
            <button onClick={() => {
              const v = view.current;
              if (!v) return;
              const next = insertMarker(v.state.doc.toString(), v.state.selection.main.head);
              const from = next.caret - (SPLIT_MARKER.length + 1);
              v.dispatch({ changes: { from, insert: `${SPLIT_MARKER} \n` }, selection: { anchor: next.caret } });
              v.focus();
            }}>Insert split here</button>
            <button disabled={!text.includes(SPLIT_MARKER) || split.isPending} onClick={() => {
              const differs = firstTextDifference(original, text);
              if (differs !== null) {
                setProblem(`Split doesn't save text edits — undo them or use Edit Source (line ${differs} differs)`);
                return;
              }
              const cuts = cutsFromText(text);
              setProblem(cuts.length ? null : "Place at least one split marker between two lines.");
              if (cuts.length) split.mutate(cuts);
            }}>Split</button>
          </>
        )}
        <Link to={`/documents/${id}`} onClick={leave}>Cancel</Link>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
    </main>
  );
}
