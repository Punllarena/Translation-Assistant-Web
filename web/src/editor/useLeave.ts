import { useCallback, useEffect, useState } from "react";
import { useBlocker, useNavigate } from "react-router";
import type { SaveState, SaveStore } from "./saveStore";

/**
 * Leave the chapter: flush first, and stay (with `notice`) while the last edits failed to save.
 * The notice clears when the next leave starts and when the save state is back to saved.
 */
export function useLeave(store: SaveStore, saveState: SaveState) {
  const navigate = useNavigate();
  const [notice, setNotice] = useState<string | null>(null);
  useEffect(() => {
    if (saveState === "saved") setNotice(null);
  }, [saveState]);
  const leave = useCallback(async (to: string) => {
    setNotice(null);
    await store.flush();
    if (store.getState().state === "error") {
      setNotice("Not moved: the last changes are not saved yet");
      return;
    }
    navigate(to);
  }, [store, navigate]);
  return { leave, notice };
}

/**
 * Links outside the editor (the app header) don't pass through `leave`, so catch them here: wait for the
 * save, then go on, or return the blocker for the caller to ask when it failed. The sign-in redirect
 * after a 401 always passes; the stash is restored after it.
 */
export function useLeaveGuard(store: SaveStore) {
  const blocker = useBlocker(({ currentLocation, nextLocation }) =>
    store.pending() && nextLocation.pathname !== currentLocation.pathname && nextLocation.pathname !== "/login");
  const [failed, setFailed] = useState(false);
  const { state, proceed } = blocker;
  useEffect(() => {
    if (state !== "blocked") return setFailed(false);
    let live = true;
    void store.flush().then(() => {
      if (!live) return;
      if (store.getState().state === "error") setFailed(true);
      else proceed?.();
    });
    return () => { live = false; };
  }, [state, proceed, store]);
  return failed ? blocker : null;
}
