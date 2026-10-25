import { collator, type SeriesCard, type SeriesRow } from "./shelf";

export type SeriesStatus = SeriesRow["status"];
export type SeriesSource = SeriesRow["source"];

export const STATUS_LABEL: Record<SeriesStatus, string> = {
  ongoing: "Ongoing", on_hold: "On hold", dropped: "Dropped", completed: "Completed",
};
export const SOURCE_LABEL: Record<SeriesSource, string> = { syosetu: "Syosetu", epub: "EPUB", other: "Other" };

export type SortKey = "modified" | "syosetu" | "added" | "title" | "progress" | "published" | "chapters";
export type SortDir = "asc" | "desc";
export interface LibrarySort { key: SortKey; dir: SortDir }

export const SORT_LABEL: Record<SortKey, string> = {
  modified: "Last modified", syosetu: "Latest syosetu update", added: "Latest added", title: "Title",
  progress: "Progress", published: "Last published", chapters: "Chapter count",
};
export const DEFAULT_DIR: Record<SortKey, SortDir> = {
  modified: "desc", syosetu: "desc", added: "desc", title: "asc", progress: "desc", published: "desc", chapters: "desc",
};
export const DEFAULT_SORT: LibrarySort = { key: "modified", dir: "desc" };

export interface LibraryFilters {
  sources: SeriesSource[];
  statuses: SeriesStatus[];
  wordpress: "any" | "published" | "none";
  archived: "hide" | "include" | "only";
}
export const DEFAULT_FILTERS: LibraryFilters = { sources: [], statuses: [], wordpress: "any", archived: "hide" };

/** Groups AND together, ticks within a group OR; an empty group matches everything. */
export function filterCards(cards: SeriesCard[], f: LibraryFilters, search: string): SeriesCard[] {
  const needle = search.trim().toLowerCase();
  return cards.filter(({ series: s, hasPublished }) => {
    if (needle && !s.title.toLowerCase().includes(needle)) return false;
    if (f.sources.length > 0 && !f.sources.includes(s.source)) return false;
    if (f.statuses.length > 0 && !f.statuses.includes(s.status)) return false;
    if (f.wordpress === "published" && !hasPublished) return false;
    if (f.wordpress === "none" && hasPublished) return false;
    const archived = s.archived_at != null;
    if (f.archived === "hide" && archived) return false;
    if (f.archived === "only" && !archived) return false;
    return true;
  });
}

/** The sortable value, or null when the series has none (those go last in either direction). */
function value(c: SeriesCard, key: SortKey): number | string | null {
  switch (key) {
    case "modified": return c.editedAt;
    case "syosetu": return c.series.syosetu_updated_at ?? null;
    case "added": return c.addedAt;
    case "published": return c.publishedAt;
    case "progress": return c.progress;
    case "chapters": return c.chapterCount;
    case "title": return c.series.title;
  }
}

function compareValues(a: number | string, b: number | string): number {
  if (typeof a === "number" && typeof b === "number") return a - b;
  if (typeof a === "string" && typeof b === "string") return collator.compare(a, b);
  return 0;
}

export function sortCards(cards: SeriesCard[], s: LibrarySort): SeriesCard[] {
  const sign = s.dir === "asc" ? 1 : -1;
  // Dates are ISO strings; the title key is the only string compared by the collator.
  const cmp = (x: number | string, y: number | string) =>
    s.key === "title" || typeof x === "number" ? compareValues(x, y) : x < y ? -1 : x > y ? 1 : 0;
  return [...cards].sort((a, b) => {
    const va = value(a, s.key);
    const vb = value(b, s.key);
    if (va === null && vb !== null) return 1;
    if (vb === null && va !== null) return -1;
    const by = va !== null && vb !== null ? sign * cmp(va, vb) : 0;
    return by || collator.compare(a.series.title, b.series.title);
  });
}

/** How many of the four filter groups differ from the default. */
export function activeGroups(f: LibraryFilters): number {
  return (f.sources.length > 0 ? 1 : 0) + (f.statuses.length > 0 ? 1 : 0)
    + (f.wordpress !== DEFAULT_FILTERS.wordpress ? 1 : 0) + (f.archived !== DEFAULT_FILTERS.archived ? 1 : 0);
}

/** Why the Library shows nothing: no series at all, only archived ones hidden, or filters/search excluding all. */
export function emptyReason(all: SeriesCard[], f: LibraryFilters, search: string): "none" | "all-archived" | "search" | "no-match" {
  if (all.length === 0) return "none";
  if (f.archived === "hide" && all.every((c) => c.series.archived_at != null)) return "all-archived";
  if (activeGroups(f) === 0 && search.trim() !== "") return "search";
  return "no-match";
}
