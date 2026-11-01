export type SaveState = "saved" | "saving" | "unsaved" | "error";
export interface Edit {
  line_number: number;
  translated_text: string;
}
interface Snapshot {
  state: SaveState;
  error: string | null;
}

/** The dirty-lines store (spec §5). Edits are kept per line; a debounced flush sends
 *  them, and an edit is forgotten only when the server accepted that exact text, so a
 *  keystroke during a save, or a failed save, is never reported as saved. */
export function createSaveStore({
  save,
  delayMs = 800,
}: {
  save: (edits: Edit[], keepalive: boolean) => Promise<void>;
  delayMs?: number;
}) {
  const dirty = new Map<number, string>();
  const listeners = new Set<() => void>();
  let snapshot: Snapshot = { state: "saved", error: null };
  let timer: ReturnType<typeof setTimeout> | undefined;
  let inFlight: Promise<void> | null = null;
  let again = false;
  let waiters: Array<() => void> = [];

  /** A new state keeps the last error until something says the server is back: a save that
   *  gets through clears it, so the message never flickers between attempts. */
  const set = (state: SaveState, error: string | null = state === "saved" ? null : snapshot.error) => {
    snapshot = { state, error };
    listeners.forEach((fn) => fn());
  };
  const schedule = () => {
    clearTimeout(timer);
    timer = setTimeout(() => void flush(), delayMs);
  };
  // ponytail: the API takes 5000 lines a batch; a chapter's dirty set is far smaller
  const unsaved = (): Edit[] =>
    [...dirty].slice(0, 5000).map(([line_number, translated_text]) => ({ line_number, translated_text }));

  function edit(line: number, text: string) {
    dirty.set(line, text);
    if (!inFlight) set("unsaved");
    schedule();
  }

  /** Saves everything dirty. Never rejects: failures are reported via getState().
   *  Called during a save, it resolves once a follow-up save covering the edits made so
   *  far has finished (or failed). */
  function flush(): Promise<void> {
    clearTimeout(timer);
    if (inFlight) {
      again = true;
      return new Promise((resolve) => waiters.push(resolve));
    }
    if (!dirty.size) {
      set("saved");
      return Promise.resolve();
    }
    // Capture exactly the batch sent; only these lines may be cleared on success.
    const batch = unsaved();
    const sent = new Map(batch.map((e) => [e.line_number, e.translated_text]));
    set("saving");
    // Deferred so a synchronous throw from save becomes an error state.
    inFlight = Promise.resolve()
      .then(() => save(batch, false))
      .then(
        () => {
          for (const [n, t] of sent) if (dirty.get(n) === t) dirty.delete(n);
          // The server answered, so an earlier failure is over even if newer edits remain.
          set(dirty.size ? "unsaved" : "saved", null);
          if (dirty.size) schedule();
        },
        (e: unknown) => set("error", e instanceof Error ? e.message : String(e)),
      )
      .finally(() => {
        inFlight = null;
        const done = waiters;
        waiters = [];
        if (again) {
          again = false;
          void flush().then(() => done.forEach((resolve) => resolve()));
        } else {
          done.forEach((resolve) => resolve());
        }
      });
    return inFlight;
  }

  /** Page hide: send everything with keepalive; nothing can be awaited any more. */
  function flushOnExit() {
    if (!dirty.size) return;
    try {
      save(unsaved(), true).catch(() => {});
    } catch {
      // nothing can be done during page hide
    }
  }

  return {
    edit,
    flush,
    flushOnExit,
    unsaved,
    pending: () => dirty.size > 0 || inFlight !== null,
    subscribe(fn: () => void) {
      listeners.add(fn);
      return () => void listeners.delete(fn);
    },
    getState: () => snapshot,
  };
}

export type SaveStore = ReturnType<typeof createSaveStore>;
