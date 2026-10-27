import type { Ruby } from "./ruby";

export interface Span {
  from: number;
  to: number;
  cls: string;
}

export interface Segment {
  text: string;
  classes: string[];
}

const CLASSES: [RegExp, string][] = [
  [/[\p{Script=Han}々〆ヵヶ]/u, "jp-kanji"],
  [/\p{Script=Hiragana}/u, "jp-hiragana"],
  [/[\p{Script=Katakana}ー]/u, "jp-katakana"],
  [/[　-〿！-／：-＠［-｀｛-･…‥]/u, "jp-punct"],
];

/** Runs of kanji, hiragana, katakana and Japanese punctuation, in UTF-16 offsets. */
export function jpSpans(text: string): Span[] {
  const spans: Span[] = [];
  let at = 0;
  for (const ch of text) {
    const cls = CLASSES.find(([re]) => re.test(ch))?.[1];
    const last = spans[spans.length - 1];
    if (cls && last && last.cls === cls && last.to === at) last.to += ch.length;
    else if (cls) spans.push({ from: at, to: at + ch.length, cls });
    at += ch.length;
  }
  return spans;
}

/** The text cut at every span edge; each piece carries the classes of the spans that
 *  cover it. Spans may overlap; they are clamped to the text and empty ones dropped. */
export function segments(text: string, spans: Span[]): Segment[] {
  const live = spans
    .map((s) => ({ ...s, from: Math.max(0, s.from), to: Math.min(text.length, s.to) }))
    .filter((s) => s.to > s.from);
  const cuts = [...new Set([0, text.length, ...live.flatMap((s) => [s.from, s.to])])].sort((a, b) => a - b);
  const out: Segment[] = [];
  for (let i = 0; i + 1 < cuts.length; i++) {
    const [a, b] = [cuts[i], cuts[i + 1]];
    out.push({ text: text.slice(a, b), classes: live.filter((s) => s.from <= a && s.to >= b).map((s) => s.cls) });
  }
  return out;
}

export type Piece =
  | { kind: "text"; seg: Segment }
  | { kind: "ruby"; base: Segment[]; rt: string; rtClasses: string[] };

const CUT = "\0cut";
const LATIN = /[A-Za-z]/;

/** `segments`, also cut at every ruby base and hidden-reading edge: text under a ruby's
 *  `hide` is not drawn, segments in a base go into that ruby's piece. The reading gets
 *  `find-current` when such a span overlaps its hidden text, and `rt-latin` when it is romaji. */
export function layout(text: string, spans: Span[], ruby: Ruby[]): Piece[] {
  const cuts: Span[] = ruby.flatMap((r) => [
    { from: r.from, to: r.to, cls: CUT },
    ...(r.hide ? [{ from: r.hide[0], to: r.hide[1], cls: CUT }] : []),
  ]);
  const out: Piece[] = [];
  const pieceOf = new Map<Ruby, Extract<Piece, { kind: "ruby" }>>();
  let at = 0;
  for (const seg of segments(text, [...spans, ...cuts])) {
    const [a, b] = [at, at + seg.text.length];
    at = b;
    if (ruby.some((r) => r.hide && r.hide[0] <= a && r.hide[1] >= b)) continue;
    const clean: Segment = { text: seg.text, classes: seg.classes.filter((c) => c !== CUT) };
    const r = ruby.find((x) => x.from <= a && x.to >= b && x.to > x.from);
    if (!r) {
      out.push({ kind: "text", seg: clean });
      continue;
    }
    let piece = pieceOf.get(r);
    if (!piece) {
      const hit = r.hide && spans.some((s) => s.cls === "find-current" && s.from < r.hide![1] && s.to > r.hide![0]);
      const rtClasses = [...(hit ? ["find-current"] : []), ...(LATIN.test(r.rt) ? ["rt-latin"] : [])];
      piece = { kind: "ruby", base: [], rt: r.rt, rtClasses };
      pieceOf.set(r, piece);
      out.push(piece);
    }
    piece.base.push(clean);
  }
  return out;
}
