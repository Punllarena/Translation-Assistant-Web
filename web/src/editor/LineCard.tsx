import { memo, useEffect, useMemo, useRef, type ReactNode } from "react";
import type { Schemas } from "../api/client";
import type { Hit } from "./find";
import { jpSpans, layout, type Segment, type Span } from "./paint";
import { sentenceRanges } from "./parse";
import type { Line } from "./rows";
import { authorRuby, type Ruby } from "./ruby";

export type Misspelling = Schemas["Misspelling"];
export const NONE: Misspelling[] = [];

const NO_RUBY: Ruby[] = [];

function Seg({ s }: { s: Segment }) {
  return s.classes.length ? <span className={s.classes.join(" ")}>{s.text}</span> : <>{s.text}</>;
}

export function Painted({ text, spans, ruby = NO_RUBY }: { text: string; spans: Span[]; ruby?: Ruby[] }) {
  return (
    <>
      {layout(text, spans, ruby).map((p, i) =>
        p.kind === "text" ? (
          <Seg key={i} s={p.seg} />
        ) : (
          <ruby key={i}>
            {p.base.map((s, j) => <Seg key={j} s={s} />)}
            <rp>(</rp><rt className={p.rtClasses.join(" ") || undefined}>{p.rt}</rt><rp>)</rp>
          </ruby>
        ),
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
  readings?: Ruby[]; // the active card's complete ruby list (generated + author), when the reading aid is on
}

/** One source paragraph and its translation. The active card holds the CodeMirror
 *  editor; the others are painted text. */
function LineCard({ index, line, active, parse, text, highlight, misspelled, onActivate, editor, readings }: Props) {
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
  const ruby = useMemo(() => readings ?? authorRuby(source), [readings, source]);
  const textSpans = useMemo(() => {
    const spans: Span[] = misspelled.map((m) => ({ from: m.start, to: m.end, cls: "misspelled" }));
    if (highlight?.field === "translation") spans.push({ from: highlight.from, to: highlight.to, cls: "find-current" });
    return spans;
  }, [misspelled, highlight]);
  return (
    <article ref={ref} className={active ? "card active" : "card"} aria-current={active || undefined}
      onClick={() => { if (!active) onActivate(index); }}>
      <span className="card-number">{line.line_number + 1}</span>
      <p className={readings?.length ? "source with-readings" : "source"} lang="ja">
        <Painted text={source} spans={sourceSpans} ruby={ruby} />
      </p>
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
