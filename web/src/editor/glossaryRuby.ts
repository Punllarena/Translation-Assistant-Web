// Glossary marks become ruby over the original text (pure). Offsets are UTF-16
// (JavaScript string indexes); marks and readings never overlap after these helpers.
import type { Schemas } from "../api/client";
import type { Ruby } from "./ruby";

export type GlossaryMark = Schemas["GlossaryMark"];

const overlaps = (a: number, b: number, c: number, d: number) => a < d && c < b;

/** Each glossary mark as ruby over the original text, dropping any mark that overlaps an
 *  author ruby range or its hidden bracket range (author ruby keeps priority). */
export function marksToRuby(marks: GlossaryMark[], author: Ruby[]): Ruby[] {
  return marks
    .filter(
      (m) =>
        !author.some(
          (a) =>
            overlaps(m.from, m.to, a.from, a.to) ||
            (a.hide !== undefined && overlaps(m.from, m.to, a.hide[0], a.hide[1])),
        ),
    )
    .map((m) => ({ from: m.from, to: m.to, rt: m.translation, cls: "rt-glossary" }));
}

/** Glossary ruby wins over generated reading ruby: a reading overlapping a glossary entry
 *  is dropped. The result is sorted by `from`. */
export function mergeReadings(glossary: Ruby[], readings: Ruby[]): Ruby[] {
  return [
    ...glossary,
    ...readings.filter((r) => !glossary.some((g) => overlaps(r.from, r.to, g.from, g.to))),
  ].sort((a, b) => a.from - b.from);
}

/** Map a replaced-text offset to the original text through the marks: outside a mark the
 *  offset shifts by the cumulative length difference, and inside one it maps to the mark's
 *  start for the left edge and end for the right edge. Never throws. */
export function shownToPlain(marks: GlossaryMark[], pos: number): number {
  let delta = 0;
  for (const m of marks) {
    if (pos <= m.shown_from) return pos - delta;
    if (pos < m.shown_to) {
      if (m.shown_to <= m.shown_from) continue; // degenerate, cannot happen
      const t = (pos - m.shown_from) / (m.shown_to - m.shown_from);
      return Math.round(m.from + t * (m.to - m.from));
    }
    delta += m.shown_to - m.shown_from - (m.to - m.from);
  }
  return pos - delta;
}
