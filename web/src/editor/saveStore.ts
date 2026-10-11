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

  const set = (state: SaveState, error: string | null = null) => {
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

  function flush(): Promise<void> {
    clearTimeout(timer);
    if (inFlight) {
      again = true;
      return inFlight;
    }
    if (!dirty.size) {
      set("saved");
      return Promise.resolve();
    }
    const sent = new Map(dirty);
    set("saving");
    inFlight = save(unsaved(), false)
      .then(
        () => {
          for (const [n, t] of sent) if (dirty.get(n) === t) dirty.delete(n);
          set(dirty.size ? "unsaved" : "saved");
          if (dirty.size) schedule();
        },
        (e: unknown) => set("error", e instanceof Error ? e.message : String(e)),
      )
      .finally(() => {
        inFlight = null;
        if (again) {
          again = false;
          void flush();
        }
      });
    return inFlight;
  }

  /** Page hide: send everything with keepalive; nothing can be awaited any more. */
  function flushOnExit() {
    if (dirty.size) save(unsaved(), true).catch(() => {});
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
