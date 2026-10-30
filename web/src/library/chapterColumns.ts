/** The chapter table's columns: their ids, labels and display order, and the rules for the
 *  account setting `series_columns` (spec §1). */

export type ColumnId =
  | "num" | "title" | "progress" | "edited" | "wp" | "original" | "images" | "lines"
  | "translated" | "chars" | "words" | "wp_date" | "ollama" | "source" | "added";

export interface Column {
  id: ColumnId;
  label: string;
  /** Only meaningful while WordPress is set up. */
  wp?: true;
}

/** Every column, in display order. */
export const COLUMNS: Column[] = [
  { id: "num", label: "#" },
  { id: "title", label: "Chapter" },
  { id: "progress", label: "Progress" },
  { id: "edited", label: "Edited" },
  { id: "wp", label: "WordPress", wp: true },
  { id: "original", label: "Original title" },
  { id: "images", label: "Images" },
  { id: "lines", label: "Lines" },
  { id: "translated", label: "Translated" },
  { id: "chars", label: "Characters" },
  { id: "words", label: "Words (EN)" },
  { id: "wp_date", label: "WP date", wp: true },
  { id: "ollama", label: "Ollama" },
  { id: "source", label: "Source" },
  { id: "added", label: "Added" },
];

export const DEFAULT_COLUMNS: ColumnId[] = ["num", "title", "progress", "edited", "wp"];

/** Columns the user cannot hide. */
export const FORCED_COLUMNS: ColumnId[] = ["num", "title"];

const known = (v: unknown): v is ColumnId =>
  typeof v === "string" && COLUMNS.some((c) => c.id === v);

/** A stored value (account setting or localStorage) as a column set: not a list means the
 *  defaults, unknown ids are dropped and # and Chapter are always there, so a value naming a
 *  column that no longer exists never leaves a blank table. In display order. */
export function parseColumns(v: unknown): ColumnId[] {
  if (!Array.isArray(v)) return DEFAULT_COLUMNS;
  const chosen = new Set(v.filter(known));
  for (const id of FORCED_COLUMNS) chosen.add(id);
  return COLUMNS.filter((c) => chosen.has(c.id)).map((c) => c.id);
}

/** The columns actually rendered; the WordPress ones need WordPress to be set up. */
export function shownColumns(chosen: ColumnId[], wpConfigured: boolean): ColumnId[] {
  return wpConfigured ? chosen : chosen.filter((id) => id !== "wp" && id !== "wp_date");
}

/** The set with `id` added or removed; # and Chapter cannot be hidden. */
export function toggleColumn(chosen: ColumnId[], id: ColumnId): ColumnId[] {
  if (FORCED_COLUMNS.includes(id)) return chosen;
  return parseColumns(chosen.includes(id) ? chosen.filter((c) => c !== id) : [...chosen, id]);
}

/** Column widths in rem, padding included. They live here, not in CSS em: fixed table layout
 *  takes widths from the 12px header cells, so em would size each column for header text. Each
 *  fits the column's longest usual value and its header label. The title takes what is left. */
const WIDTH_REM: Record<Exclude<ColumnId, "title">, number> = {
  num: 3, progress: 6.25, edited: 6, wp: 6.5, original: 9, images: 4.25, lines: 4.25,
  translated: 6.5, chars: 6.5, words: 6.5, wp_date: 8.75, ollama: 5.5, source: 4.75, added: 6,
};
/** The drag grip, checkbox and ⋯ menu columns. */
export const EDGE_REM = { grip: 2.25, check: 2, menu: 3.5 };
/** The least the title keeps before the table scrolls sideways in its own box. */
const TITLE_MIN_REM = 10;
/** Columns the phone layout hides (`library.css`, max-width 767px). */
const NARROW_HIDDEN: ColumnId[] = ["progress", "edited", "wp"];

export const columnWidth = (id: ColumnId): string | undefined =>
  id === "title" ? undefined : `${WIDTH_REM[id]}rem`;

/** The table's min-width in rem: the shown fixed columns plus room for the title. `grip` is
 *  false in select mode (the grip column is hidden); `narrow` leaves out what phones hide. */
export function tableMinWidthRem(columns: ColumnId[], { grip, narrow }: { grip: boolean; narrow: boolean }): number {
  let rem = EDGE_REM.check + EDGE_REM.menu + TITLE_MIN_REM + (grip && !narrow ? EDGE_REM.grip : 0);
  for (const id of columns) {
    if (id === "title" || (narrow && NARROW_HIDDEN.includes(id))) continue;
    rem += WIDTH_REM[id];
  }
  return rem;
}
