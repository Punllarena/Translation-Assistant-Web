import { useEffect, useRef, useState } from "react";

const TERMINAL = new Set(["needs_setup", "error", "done"]);

/** One debounced (300 ms) EventSource folded into a state by `apply`. A new `url` or `nonce`
 * opens a new stream; null closes it and resets to `initial`. Every reducer handles "error",
 * which a dropped connection also reports. `onEvent` sees each event after it is applied. */
export function useSse<S>(opts: {
  url: string | null; nonce?: unknown; events: string[];
  apply(state: S, type: string, data: unknown): S; initial: S; start: S;
  onEvent?(type: string, data: unknown): void;
}): S {
  const { url, nonce } = opts;
  const [state, setState] = useState<S>(opts.initial);
  const latest = useRef(opts);
  latest.current = opts;
  useEffect(() => {
    const { apply, initial, start, events } = latest.current;
    if (url === null) { setState(initial); return; }
    setState(start);
    let es: EventSource | null = null;
    const timer = setTimeout(() => {
      const source = new EventSource(url);
      es = source;
      let heard = false;
      let terminal = false;
      for (const type of events) {
        source.addEventListener(type, (e) => {
          heard = true;
          let data: unknown = {};
          try { data = JSON.parse((e as MessageEvent).data); } catch { /* keep {} */ }
          setState((s) => apply(s, type, data));
          latest.current.onEvent?.(type, data);
          if (TERMINAL.has(type)) { terminal = true; source.close(); }
        });
      }
      source.onerror = () => {
        if (!terminal) setState((s) => apply(s, "error", { message: heard ? "Connection lost" : "Connection failed" }));
        source.close();
      };
    }, 300);
    return () => { clearTimeout(timer); es?.close(); };
  }, [url, nonce]);
  return state;
}
