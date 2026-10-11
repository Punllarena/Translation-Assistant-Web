import type { Schemas } from "../api/client";

export type Doc = Schemas["DocumentListItem"];
export type SeriesRow = Schemas["SeriesOut"];
export interface Group {
  series: SeriesRow | null;
  docs: Doc[];
}

const natural = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });

/** The picker's groups: series in natural title order, each with its chapters in reading
 *  order, then unsorted documents, most recently edited first. A filter matches a document
 *  title, a chapter title, or a series title (which shows the whole series). */
export function groupDocuments(docs: Doc[], series: SeriesRow[], filter: string): Group[] {
  const q = filter.trim().toLocaleLowerCase();
  const has = (s: string) => s.toLocaleLowerCase().includes(q);
  const bySeries = new Map<number | null, Doc[]>();
  for (const d of docs) {
    const list = bySeries.get(d.series_id) ?? [];
    list.push(d);
    bySeries.set(d.series_id, list);
  }
  const groups: Group[] = [...series]
    .sort((a, b) => natural.compare(a.title, b.title))
    .map((s) => ({
      series: s,
      docs: (bySeries.get(s.id) ?? []).sort((a, b) => a.series_order - b.series_order || a.id - b.id),
    }));
  groups.push({
    series: null,
    docs: (bySeries.get(null) ?? []).sort((a, b) => b.updated_at.localeCompare(a.updated_at)),
  });
  if (!q) return groups.filter((g) => g.series || g.docs.length);
  return groups
    .map((g) =>
      g.series && has(g.series.title)
        ? g
        : { ...g, docs: g.docs.filter((d) => has(d.title) || has(d.chapter_title)) },
    )
    .filter((g) => g.docs.length);
}
