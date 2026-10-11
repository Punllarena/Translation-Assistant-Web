/** Parse navigation (desktop _advance_parse / _retreat_parse). The pointer is a sentence
 *  index; -1 shows the glossary-substituted line, -2 the raw line (only reachable when
 *  the glossary changed something). */
export const advanceParse = (p: number, count: number) => (p + 1 < count ? p + 1 : p);

export const retreatParse = (p: number, replaced: boolean) =>
  p - 1 >= (replaced ? -2 : -1) ? p - 1 : p;

/** Each sentence's [from, to) in the display text, searched in order so a repeated
 *  sentence maps to its own occurrence (the desktop always found the first). */
export function sentenceRanges(display: string, sentences: string[]): [number, number][] {
  const ranges: [number, number][] = [];
  let at = 0;
  for (const s of sentences) {
    const i = display.indexOf(s, at);
    if (i < 0) {
      ranges.push([0, 0]);
      continue;
    }
    ranges.push([i, i + s.length]);
    at = i + s.length;
  }
  return ranges;
}
