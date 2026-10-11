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
