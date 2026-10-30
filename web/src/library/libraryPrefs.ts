import {
  DEFAULT_DIR, DEFAULT_FILTERS, DEFAULT_SORT, SOURCE_LABEL, STATUS_LABEL,
  type LibraryFilters, type LibrarySort, type SortKey,
} from "./libraryQuery";

const SORT_KEY = "ta.librarySort";
const FILTERS_KEY = "ta.libraryFilters";

const isSortKey = (k: unknown): k is SortKey => typeof k === "string" && Object.hasOwn(DEFAULT_DIR, k);

function readJson(key: string, storage?: Pick<Storage, "getItem">): Record<string, unknown> | null {
  try {
    const raw = (storage ?? window.localStorage).getItem(key);
    const v: unknown = raw === null ? null : JSON.parse(raw);
    return v !== null && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

function writeJson(key: string, v: unknown, storage?: Pick<Storage, "setItem">): void {
  try {
    (storage ?? window.localStorage).setItem(key, JSON.stringify(v));
  } catch {
    // Blocked storage: the choice still applies for this page load.
  }
}

/** Any stored or server value to a sort: a bad key or direction falls back as a whole. */
export function parseSort(v: unknown): LibrarySort {
  if (v !== null && typeof v === "object" && !Array.isArray(v)) {
    const o = v as Record<string, unknown>;
    if (isSortKey(o.key) && (o.dir === "asc" || o.dir === "desc")) return { key: o.key, dir: o.dir };
  }
  return DEFAULT_SORT;
}

/** Storage can be missing or throw (private windows, blocked site data). */
export function readSort(storage?: Pick<Storage, "getItem">): LibrarySort {
  return parseSort(readJson(SORT_KEY, storage));
}

export function writeSort(s: LibrarySort, storage?: Pick<Storage, "setItem">): void {
  writeJson(SORT_KEY, s, storage);
}

const known = <T extends string>(v: unknown, labels: Record<T, string>): T[] =>
  Array.isArray(v) ? v.filter((x): x is T => typeof x === "string" && Object.hasOwn(labels, x)) : [];
const oneOf = <T extends string>(v: unknown, options: readonly T[], fallback: T): T =>
  options.find((o) => o === v) ?? fallback;

/** Any stored or server value to filters: each field falls back on its own, so one unknown tick
 *  never blanks the others. */
export function parseFilters(v: unknown): LibraryFilters {
  if (v === null || typeof v !== "object" || Array.isArray(v)) return DEFAULT_FILTERS;
  const o = v as Record<string, unknown>;
  return {
    sources: known(o.sources, SOURCE_LABEL),
    statuses: known(o.statuses, STATUS_LABEL),
    wordpress: oneOf(o.wordpress, ["any", "published", "none"], DEFAULT_FILTERS.wordpress),
    archived: oneOf(o.archived, ["hide", "include", "only"], DEFAULT_FILTERS.archived),
  };
}

export function readFilters(storage?: Pick<Storage, "getItem">): LibraryFilters {
  return parseFilters(readJson(FILTERS_KEY, storage));
}

export function writeFilters(f: LibraryFilters, storage?: Pick<Storage, "setItem">): void {
  writeJson(FILTERS_KEY, f, storage);
}
