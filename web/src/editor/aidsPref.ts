const KEY = "ta.aidsOpen";

/** Whether the aid column starts open. Storage can be missing or throw (private windows, blocked
 *  site data): open is the default, and the page works without it. */
export function readAidsOpen(storage?: Pick<Storage, "getItem">): boolean {
  try {
    return (storage ?? window.localStorage).getItem(KEY) !== "false";
  } catch {
    return true;
  }
}

export function writeAidsOpen(open: boolean, storage?: Pick<Storage, "setItem">): void {
  try {
    (storage ?? window.localStorage).setItem(KEY, String(open));
  } catch {
    // Blocked storage: the choice still applies for this page load.
  }
}
