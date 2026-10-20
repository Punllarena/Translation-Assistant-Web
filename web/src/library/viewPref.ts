export type LibraryView = "shelf" | "list";

const KEY = "ta.libraryView";

/** Storage can be missing or throw (private windows, blocked site data). */
export function readView(storage?: Pick<Storage, "getItem">): LibraryView {
  try {
    return (storage ?? window.localStorage).getItem(KEY) === "list" ? "list" : "shelf";
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
