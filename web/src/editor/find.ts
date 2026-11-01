export interface Hit {
  index: number; // array index of the line
  field: "source" | "translation";
  from: number;
  to: number;
}

/** No hits, as one shared array, so a memoised card is not re-rendered for a new empty one. */
export const NO_HITS: Hit[] = [];

const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** Case-insensitive occurrences of `needle`, as UTF-16 [from, to). */
export function findIn(text: string, needle: string): [number, number][] {
  if (!needle) return [];
  return [...text.matchAll(new RegExp(escape(needle), "giu"))].map(
    (m) => [m.index, m.index + m[0].length] as [number, number],
  );
}

export function findHits(
  items: { index: number; source: string; translation: string }[],
  needle: string,
): Hit[] {
  return items.flatMap((item) => [
    ...findIn(item.source, needle).map(([from, to]) => ({ index: item.index, field: "source" as const, from, to })),
    ...findIn(item.translation, needle).map(([from, to]) => ({ index: item.index, field: "translation" as const, from, to })),
  ]);
}

/** The next position after `current` in `dir`, wrapping; -1 when there is nothing. */export function wrapStep(current: number, total: number, dir: 1 | -1): number {
  if (total === 0) return -1;
  if (current < 0) return dir === 1 ? 0 : total - 1;
  return (current + dir + total) % total;
}

/** The first hit on or after the active line, else the first hit; -1 when none. */
export function firstFrom(hits: Hit[], active: number): number {
  if (!hits.length) return -1;
  const i = hits.findIndex((h) => h.index >= active);
  return i < 0 ? 0 : i;
}
