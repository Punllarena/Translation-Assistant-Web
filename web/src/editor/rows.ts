import type { Schemas } from "../api/client";

export type Line = Schemas["LineOut"];
export type Image = Schemas["ImageOut"];
export type Row = { kind: "line"; line: Line; index: number } | { kind: "image"; image: Image };

/** A line with translatable text (desktop core.line_has_content). */
export const hasContent = (raw: string) => raw.replace(/^[%$]+/, "").trim() !== "";

/** Cards in reading order (desktop card_list.load): an image anchored at n sits before
 *  line n, images anchored past the end go last, and blank lines get no card. */
export function buildRows(lines: Line[], images: Image[]): Row[] {
  const sorted = [...images].sort((a, b) => a.anchor_position - b.anchor_position || a.id - b.id);
  const rows: Row[] = [];
  let next = 0;
  lines.forEach((line, index) => {
    while (next < sorted.length && sorted[next].anchor_position <= line.line_number) {
      rows.push({ kind: "image", image: sorted[next++] });
    }
    if (hasContent(line.raw_text)) rows.push({ kind: "line", line, index });
  });
  while (next < sorted.length) rows.push({ kind: "image", image: sorted[next++] });
  return rows;
}

export function nextContent(lines: Line[], from: number): number | null {
  for (let i = from + 1; i < lines.length; i++) if (hasContent(lines[i].raw_text)) return i;
  return null;
}

export function prevContent(lines: Line[], from: number): number | null {
  for (let i = from - 1; i >= 0; i--) if (hasContent(lines[i].raw_text)) return i;
  return null;
}

export const firstContent = (lines: Line[]) => nextContent(lines, -1);

/** The first translatable line without a translation, from the top (desktop
 *  _jump_to_next_untranslated). */
export function firstUntranslated(lines: Line[], texts: Record<number, string>): number | null {
  const i = lines.findIndex((l) => hasContent(l.raw_text) && !texts[l.line_number]);
  return i < 0 ? null : i;
}

/** Go to line: 1-based n, clamped, moved forward (else back) to a translatable line. */
export function lineAtOrAfter(lines: Line[], n: number): number | null {
  if (!lines.length) return null;
  const i = Math.max(0, Math.min(lines.length - 1, n - 1));
  return hasContent(lines[i].raw_text) ? i : (nextContent(lines, i) ?? prevContent(lines, i));
}

/** The desktop calculate_progress rules, except that an empty translation counts no
 *  words (the desktop's "".split(" ") counted one). */
export function progress(lines: Line[], texts: Record<number, string>) {
  let total = 0;
  let done = 0;
  let words = 0;
  for (const l of lines) {
    const t = texts[l.line_number] ?? "";
    if (t) words += t.split(" ").length;
    if (hasContent(l.raw_text)) {
      total++;
      if (t) done++;
    }
  }
  return { percent: total ? Math.floor((done * 100) / total) : 0, words };
}

/** The Edit Source text: one line per line, $ kept on continuation lines. */
export const sourceText = (lines: Line[]) =>
  lines.map((l) => (l.prefix === "$" ? "$" : "") + l.raw_text).join("\n");
