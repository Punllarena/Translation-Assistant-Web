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
