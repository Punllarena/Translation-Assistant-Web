import { defaultKeymap, history, historyKeymap, insertNewline } from "@codemirror/commands";
import { EditorState, StateEffect, StateField, Transaction } from "@codemirror/state";
import { Decoration, type DecorationSet, EditorView, keymap } from "@codemirror/view";
import { useEffect, useRef } from "react";
import type { Span } from "./paint";

/** Replace the editor's highlight marks (spell, find). */
export const setMarks = StateEffect.define<Span[]>();

const marks = StateField.define<DecorationSet>({
  create: () => Decoration.none,
  update(deco, tr) {
    let next = deco.map(tr.changes);
    for (const e of tr.effects) {
      if (e.is(setMarks)) {
        next = Decoration.set(
          e.value
            .filter((m) => m.to > m.from && m.to <= tr.state.doc.length)
            .map((m) => Decoration.mark({ class: m.cls }).range(m.from, m.to)),
          true,
        );
      }
    }
    return next;
  },
  provide: (f) => EditorView.decorations.from(f),
});

/** Insert `text` over the selection; the caret lands `caretOffset` into it (the
 *  desktop puts it inside paired brackets). */
export function insertAtCursor(view: EditorView | null, text: string, caretOffset = text.length) {
  if (!view) return;
  const { from, to } = view.state.selection.main;
  view.dispatch({ changes: { from, to, insert: text }, selection: { anchor: from + caretOffset } });
  view.focus();
}

interface Props {
  value: string;
  label: string;
  onChange(text: string): void;
  onBlur?(): void;
  onReady(view: EditorView | null): void;
  autoFocus?: boolean;
  onContextMenu?(view: EditorView, e: MouseEvent): boolean;
}

/** A CodeMirror view, created once per mount (key it to replace the document). */
export default function CodeEditor({ value, label, onChange, onBlur, onReady, onContextMenu, autoFocus = true }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const latest = useRef({ onChange, onBlur, onContextMenu });
  latest.current = { onChange, onBlur, onContextMenu };
  useEffect(() => {
    const view = new EditorView({
      parent: host.current!,
      state: EditorState.create({
        doc: value,
        extensions: [
          history(),
          keymap.of([{ key: "Shift-Enter", run: insertNewline }, ...historyKeymap, ...defaultKeymap]),
          EditorView.lineWrapping,
          marks,
          EditorView.contentAttributes.of({ "aria-label": label, spellcheck: "false" }),
          EditorView.updateListener.of((u) => {
            if (u.docChanged) latest.current.onChange(u.state.doc.toString());
          }),
          EditorView.domEventHandlers({
            blur: () => latest.current.onBlur?.(),
            contextmenu: (e, v) => latest.current.onContextMenu?.(v, e) ?? false,
          }),
        ],
      }),
    });
    viewRef.current = view;
    if (autoFocus) view.focus();
    onReady(view);
    return () => {
      viewRef.current = null;
      onReady(null);
      view.destroy();
    };
    // Created once per mount by design; the parent keys this component per line.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  // External changes (a restored unsaved edit, a later programmatic edit) replace the document.
  useEffect(() => {
    const view = viewRef.current;
    if (!view || view.state.doc.toString() === value) return;
    const head = Math.min(view.state.selection.main.head, value.length);
    view.dispatch({
      changes: { from: 0, to: view.state.doc.length, insert: value }, selection: { anchor: head },
      annotations: Transaction.addToHistory.of(false), // a restore is not something Ctrl+Z undoes
    });
  }, [value]);
  return <div ref={host} className="code-editor" />;
}
