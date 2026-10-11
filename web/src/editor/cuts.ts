export const SPLIT_MARKER = "---CHAPTER SPLIT---";

/** The desktop _SplitChapterDialog._cuts: the first line of each new chapter (counting
 *  non-marker lines) and the title typed after its marker. A marker before the first
 *  line, after the last, or repeating the previous position is ignored. */
export function cutsFromText(text: string): { start: number; title: string }[] {
  const cuts: { start: number; title: string }[] = [];
  let n = 0;
  for (const raw of text.split("\n")) {
    const s = raw.trim();
    if (s.startsWith(SPLIT_MARKER)) {
      if (n >= 1 && cuts[cuts.length - 1]?.start !== n) {
        cuts.push({ start: n, title: s.slice(SPLIT_MARKER.length).trim() });
      }
    } else {
      n++;
    }
  }
  return cuts.filter((c) => c.start <= n - 1);
}

/** A marker line at the start of the caret's line; the caret lands after it, ready for
 *  the title. */
export function insertMarker(text: string, caret: number) {
  // lastIndexOf(.., -1) is treated as 0 and would match a leading newline, so guard caret 0
  const start = caret <= 0 ? 0 : text.lastIndexOf("\n", caret - 1) + 1;
  const marker = `${SPLIT_MARKER} `;
  return { text: `${text.slice(0, start)}${marker}\n${text.slice(start)}`, caret: start + marker.length };
}

/** 1-based number of the first non-marker line of `edited` that differs from `original`
 *  (counting non-marker lines only), or null when they match. A changed line count
 *  reports the first line past the shorter side. */
export function firstTextDifference(original: string, edited: string): number | null {
  const was = original.split("\n");
  const now = edited.split("\n").filter((l) => !l.trim().startsWith(SPLIT_MARKER));
  for (let i = 0; i < Math.max(was.length, now.length); i++) {
    if (was[i] !== now[i]) return i + 1;
  }
  return null;
}
