import { defaultKeymap, history, historyKeymap, insertNewline } from "@codemirror/commands";
import { EditorState, StateEffect, StateField } from "@codemirror/state";
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
  initial: string;
  label: string;
  onChange(text: string): void;
  onBlur?(): void;
  onReady(view: EditorView | null): void;
  onContextMenu?(view: EditorView, e: MouseEvent): boolean;
}

/** A CodeMirror view, created once per mount (key it to replace the document). */
export default function CodeEditor({ initial, label, onChange, onBlur, onReady, onContextMenu }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const latest = useRef({ onChange, onBlur, onContextMenu });
  latest.current = { onChange, onBlur, onContextMenu };
  useEffect(() => {
    const view = new EditorView({
      parent: host.current!,
      state: EditorState.create({
        doc: initial,
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
    view.focus();
    onReady(view);
    return () => {
      onReady(null);
      view.destroy();
    };
    // Created once per mount by design; the parent keys this component per line.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return <div ref={host} className="code-editor" />;
}
