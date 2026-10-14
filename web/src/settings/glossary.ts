export type Row = { phrase: string; translation: string };

export function moveRow(rows: Row[], i: number, dir: -1 | 1): Row[] {
  const j = i + dir;
  if (j < 0 || j >= rows.length) return rows;
  const next = rows.slice();
  [next[i], next[j]] = [next[j], next[i]];
  return next;
}

/** What Save sends: rows the user left entirely blank are dropped (desktop _on_save). */
export const toEntries = (rows: Row[]) => rows.filter((x) => x.phrase.trim() || x.translation.trim());

/** Positions in `rows` whose phrase or translation differs from the loaded glossary at the same position. */
export function changedRows(rows: Row[], loaded: Row[]): Set<number> {
  const out = new Set<number>();
  rows.forEach((row, i) => {
    const was = loaded[i];
    if (!was || was.phrase !== row.phrase || was.translation !== row.translation) out.add(i);
  });
  return out;
}

/** The "{n} unsaved changes" count: changed or added rows, plus rows removed from the end. */
export const countChanges = (rows: Row[], loaded: Row[]) =>
  changedRows(rows, loaded).size + Math.max(0, loaded.length - rows.length);
