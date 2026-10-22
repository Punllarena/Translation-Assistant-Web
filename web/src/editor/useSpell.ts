import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { api, call } from "../api/client";
import { NONE, type Misspelling } from "./LineCard";
import { spellBatches } from "./spell";

/** Misspellings per translation text, fetched in batches 500 ms after typing stops.
 *  Keyed by text, so a card's array stays identical until its text changes. */
export function useSpell(seriesId: number, texts: string[]) {
  const cache = useRef(new Map<string, Misspelling[]>());
  const [version, bump] = useReducer((n: number) => n + 1, 0);
  const [available, setAvailable] = useState(true);
  const forget = useCallback(() => {
    cache.current = new Map();
    bump();
  }, []);
  useEffect(forget, [seriesId, forget]);
  const key = texts.join("\u0000");
  useEffect(() => {
    const missing = [...new Set(texts)].filter((t) => t && !cache.current.has(t));
    if (!missing.length) return;
    let live = true;
    const timer = setTimeout(async () => {
      for (const batch of spellBatches(missing)) {
        // ponytail: spellcheck is best-effort; a failed batch is retried on the next edit
        const result = await call(api.POST("/spell/check", { body: { texts: batch, series_id: seriesId } })).catch(() => null);
        if (!live || !result) return;
        setAvailable(result.available);
        batch.forEach((t, i) => cache.current.set(t, result.results[i]));
      }
      if (live) bump();
    }, 500);
    return () => {
      live = false;
      clearTimeout(timer);
    };
    // `key` stands for `texts`; `version` re-runs after forget()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, seriesId, version]);
  const misspelled = useCallback((t: string) => cache.current.get(t) ?? NONE,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [version]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const known = useCallback((t: string) => cache.current.has(t), [version]);
  return { available, misspelled, forget, known };
}
