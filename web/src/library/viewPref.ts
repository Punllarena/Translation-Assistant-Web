export type LibraryView = "shelf" | "list";

const KEY = "ta.libraryView";

/** Any stored or server value to a view; only a bare `list` is the list view (the key has always
 *  held a bare string, not JSON). */
export function parseView(v: unknown): LibraryView {
  return v === "list" ? "list" : "shelf";
}

/** Storage can be missing or throw (private windows, blocked site data). */
export function readView(storage?: Pick<Storage, "getItem">): LibraryView {
  try {
    return parseView((storage ?? window.localStorage).getItem(KEY));
  } catch {
    return "shelf";
  }
}

export function writeView(v: LibraryView, storage?: Pick<Storage, "setItem">): void {
  try {
    (storage ?? window.localStorage).setItem(KEY, v);
  } catch {
    // Blocked storage: the view still applies for this page load.
  }
}
