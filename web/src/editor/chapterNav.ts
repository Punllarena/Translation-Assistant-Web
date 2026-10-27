import type { Doc } from "../library/shelf";

/** The chapter's neighbours within its series (by series_order) and the chapters of its volume
 *  (a null volume_id groups the loose chapters). */
export function chapterNeighbours(docs: Doc[], id: number): { prev: Doc | null; next: Doc | null; volume: Doc[] } {
  const here = docs.find((d) => d.id === id);
  if (!here) return { prev: null, next: null, volume: [] };
  const own = docs
    .filter((d) => d.series_id === here.series_id)
    .sort((a, b) => a.series_order - b.series_order || a.id - b.id);
  const at = own.findIndex((d) => d.id === id);
  return {
    prev: own[at - 1] ?? null,
    next: own[at + 1] ?? null,
    volume: own.filter((d) => d.volume_id === here.volume_id),
  };
}
