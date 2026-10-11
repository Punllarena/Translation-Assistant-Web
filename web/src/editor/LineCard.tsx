import { memo, useEffect, useMemo, useRef, type ReactNode } from "react";
import type { Schemas } from "../api/client";
import type { Hit } from "./find";
import { jpSpans, segments, type Span } from "./paint";
import { sentenceRanges } from "./parse";
import type { Line } from "./rows";

export type Misspelling = Schemas["Misspelling"];
export const NONE: Misspelling[] = [];

export function Painted({ text, spans }: { text: string; spans: Span[] }) {
  return (
    <>
      {segments(text, spans).map((s, i) =>
        s.classes.length ? <span key={i} className={s.classes.join(" ")}>{s.text}</span> : s.text,
      )}
    </>
  );
}

interface Props {
  index: number;
  line: Line;
  active: boolean;
  parse: number; // -1 unless active
  text: string;
  highlight: Hit | null;
  misspelled: Misspelling[];
  onActivate(index: number): void;
  editor?: ReactNode;
}

/** One source paragraph and its translation. The active card holds the CodeMirror
 *  editor; the others are painted text. */
function LineCard({ index, line, active, parse, text, highlight, misspelled, onActivate, editor }: Props) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    if (active) ref.current?.scrollIntoView({ block: "center" });
  }, [active]);
  const source = parse === -2 ? line.raw_text : line.display_text;
  const sourceSpans = useMemo(() => {
    const spans = jpSpans(source);
    if (parse >= 0) {
      const [from, to] = sentenceRanges(line.display_text, line.sentences)[parse] ?? [0, 0];
      spans.push({ from, to, cls: "sentence-current" });
    }
    if (highlight?.field === "source") spans.push({ from: highlight.from, to: highlight.to, cls: "find-current" });
    return spans;
  }, [source, parse, line, highlight]);
  const textSpans = useMemo(() => {
    const spans: Span[] = misspelled.map((m) => ({ from: m.start, to: m.end, cls: "misspelled" }));
    if (highlight?.field === "translation") spans.push({ from: highlight.from, to: highlight.to, cls: "find-current" });
    return spans;
  }, [misspelled, highlight]);
  return (
    <article ref={ref} className={active ? "card active" : "card"} aria-current={active || undefined}
      onClick={() => { if (!active) onActivate(index); }}>
      <span className="card-number">{line.line_number + 1}</span>
      <p className="source" lang="ja"><Painted text={source} spans={sourceSpans} /></p>
      {active ? (
        editor
      ) : (
        <p className="translation" lang="en">
          {text ? <Painted text={text} spans={textSpans} /> : <span className="muted">Type your translation…</span>}
        </p>
      )}
    </article>
  );
}

export default memo(LineCard);
