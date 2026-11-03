import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { useBlocker, useNavigate } from "react-router";
import type { SaveState, SaveStore } from "./saveStore";

/** What the user asked to do, held until the text is safe. */
interface Queued {
  go(): void;
  cancel(): void;
}

/** The lines and the error as they were when the failure was first seen. */
export interface Asking {
  lines: number[]; // 1-based
  error: string;
}

/**
 * One way out of the chapter, whatever asked for it: the arrows, the crumbs, the end card, a
 * link in the app header. The move waits for the save; a failed save opens one dialog whose
 * text cannot change under a retry; a later success carries the move out by itself, and
 * Cancel (or Esc while waiting) keeps the page where it is.
 *
 * The blocker's condition stays `store.pending()` and a different path; `/login` always passes
 * because the stash is restored after sign-in.
 */
export function useLeave(store: SaveStore, saveState: SaveState, onStay: () => void) {
  const navigate = useNavigate();
  const [queued, setQueued] = useState<Queued | null>(null);
  const [asking, setAsking] = useState<Asking | null>(null);
  // Every store change, including the in-flight flag dropping after the last state message:
  // the move must be reconsidered then, and neither of those changes the snapshot.
  const [version, bump] = useReducer((n: number) => n + 1, 0);
  useEffect(() => store.subscribe(bump), [store]);
  // Lets a go that the user confirmed pass the blocker's own condition.
  const bypass = useRef(false);
  const blocker = useBlocker(({ currentLocation, nextLocation }) =>
    !bypass.current && store.pending() && nextLocation.pathname !== currentLocation.pathname
      && nextLocation.pathname !== "/login");

  // An exit the router caught (a header link): take it over rather than let it go.
  useEffect(() => {
    if (blocker.state !== "blocked") return;
    setQueued({ go: () => blocker.proceed?.(), cancel: () => blocker.reset?.() });
    void store.flush();
  }, [blocker.state, blocker.proceed, blocker.reset, store]);

  const leave = useCallback((to: string) => {
    setAsking(null);
    bypass.current = false;
    setQueued({ go: () => navigate(to), cancel: () => setQueued(null) });
    void store.flush();
  }, [navigate, store]);

  // One place decides: go once the text is safe, ask once it is not.
  useEffect(() => {
    if (!queued) return;
    const snapshot = store.getState();
    if (snapshot.state === "error") {
      // Snapshot on the first failure only: a retry must not change what the dialog says.
      setAsking((asked) => asked ?? { lines: store.unsaved().map((e) => e.line_number + 1),
        error: snapshot.error ?? "the save failed" });
      return;
    }
    if (snapshot.state === "saved" && !store.pending()) {
      bypass.current = true;
      queued.go();
      setQueued(null);
    }
  }, [queued, saveState, store, version]);

  const stay = useCallback(() => {
    const held = queued;
    setAsking(null);
    setQueued(null);
    held?.cancel();
    onStay();
  }, [queued, onStay]);

  const goAnyway = useCallback(() => {
    const held = queued;
    setAsking(null);
    setQueued(null);
    if (!held) return;
    bypass.current = true;
    held.go();
    // The move unmounts the editor; a stay behind is the only case this has to undo.
    setTimeout(() => { bypass.current = false; }, 0);
  }, [queued]);

  const waiting = queued !== null && asking === null;
  // Esc gives up on the move without touching the text.
  useEffect(() => {
    if (!waiting) return;
    const onEsc = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.preventDefault();
      e.stopPropagation();
      stay();
    };
    window.addEventListener("keydown", onEsc, true);
    return () => window.removeEventListener("keydown", onEsc, true);
  }, [waiting, stay]);

  return { leave, waiting, asking, goAnyway, stay };
}
