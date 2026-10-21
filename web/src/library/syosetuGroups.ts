/** Syosetu's chapter-title headings, as consecutive runs of the chapter index. */
export interface GroupRun<T> { group: string | null; chapters: T[] }

export function groupRuns<T extends { group?: string | null }>(chapters: T[]): GroupRun<T>[] {
  const runs: GroupRun<T>[] = [];
  for (const ch of chapters) {
    const group = ch.group ?? null;
    const last = runs[runs.length - 1];
    if (last && last.group === group) last.chapters.push(ch);
    else runs.push({ group, chapters: [ch] });
  }
  return runs;
}
