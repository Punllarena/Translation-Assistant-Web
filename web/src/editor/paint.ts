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
