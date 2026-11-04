const KEY = "ta.aidsOpen";

/** Below 60rem the aid column pins to the foot of the screen, so it starts as a peek bar there. */
function narrowScreen(): boolean {
  try {
    return window.matchMedia("(max-width: 60rem)").matches;
  } catch {
    return false;
  }
}

/** Whether the aid column starts open: the saved choice, else open on a wide screen and folded on a narrow one.
 *  Storage can be missing or throw (private windows, blocked site data); the page works without it. */
export function readAidsOpen(storage?: Pick<Storage, "getItem">, narrow: boolean = narrowScreen()): boolean {
  try {
    const saved = (storage ?? window.localStorage).getItem(KEY);
    return saved === null ? !narrow : saved !== "false";
  } catch {
    return !narrow;
  }
}

export function writeAidsOpen(open: boolean, storage?: Pick<Storage, "setItem">): void {
  try {
    (storage ?? window.localStorage).setItem(KEY, String(open));
  } catch {
    // Blocked storage: the choice still applies for this page load.
  }
}
