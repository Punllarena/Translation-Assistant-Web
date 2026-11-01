import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, call } from "../api/client";
import { signedOutOn401 } from "../auth/session";
import type { Line } from "./rows";
import { saveFailure } from "./saveErrors";
import { createSaveStore, type Edit } from "./saveStore";

const stashKey = (id: number) => `ta-unsaved-${id}`;

async function saveLines(id: number, edits: Edit[], keepalive: boolean): Promise<number[]> {
  if (keepalive) {
    // openapi-fetch cannot set keepalive, which lets the request outlive the page.
    await fetch(`/api/documents/${id}/lines`, {
      method: "PATCH",
      keepalive: true,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lines: edits }),
    });
    return [];
  }
  const res = await call(api.PATCH("/documents/{document_id}/lines", {
    params: { path: { document_id: id } },
    body: { lines: edits },
    // A hung save must end in an error the user can act on, not silence.
    signal: AbortSignal.timeout(20_000),
  }));
  return res.missing;
}

/** Unsaved edits survive the tab closing, a crash, or a sign-in redirect in this tab:
 *  they are stashed in sessionStorage and re-sent when the chapter next opens. */
function stash(id: number, edits: Edit[]) {
  try {
    if (edits.length) sessionStorage.setItem(stashKey(id), JSON.stringify(edits));
    else sessionStorage.removeItem(stashKey(id));
  } catch {
    // storage unavailable: the keepalive save is the only net
  }
}

/** Clears the stash only if it is still exactly what `written` put there. */
function clearStashIf(id: number, written: Edit[]) {
  try {
    if (sessionStorage.getItem(stashKey(id)) === JSON.stringify(written)) sessionStorage.removeItem(stashKey(id));
  } catch {
    // storage unavailable
  }
}

function takeStash(id: number): Edit[] {
  try {
    const raw = sessionStorage.getItem(stashKey(id));
    sessionStorage.removeItem(stashKey(id));
    return raw ? (JSON.parse(raw) as Edit[]) : [];
  } catch {
    return [];
  }
}

export function useEditor(id: number, lines: Line[], startAt: number) {
  const queryClient = useQueryClient();
  const [missing, setMissing] = useState<number[]>([]);
  // Read during render, set before the store's state changes and its subscribers run.
  const permanent = useRef(false);
  const store = useMemo(
    () =>
      createSaveStore({
        // A 401 means the session expired: sign out so RequireAuth redirects to /login and
        // the stash is restored after sign-in. The store keeps showing the error until then.
        save: (edits, keepalive) =>
          saveLines(id, edits, keepalive).then(
            (m) => {
              setMissing(m);
            },
            (e) => {
              signedOutOn401(queryClient, e);
              const failure = saveFailure(e);
              permanent.current = failure.permanent;
              throw new Error(failure.message);
            },
          ),
      }),
    [id, queryClient],
  );
  const save = useSyncExternalStore(store.subscribe, store.getState);
  const [active, setActive] = useState(startAt);
  const [restored, setRestored] = useState(0);
  const retries = useRef(0);
  const [parse, setParse] = useState(-1);
  const [texts, setTexts] = useState<Record<number, string>>(() =>
    Object.fromEntries(lines.map((l) => [l.line_number, l.translated_text])),
  );
  const linesRef = useRef(lines);
  linesRef.current = lines;

  const setText = useCallback(
    (n: number, t: string) => {
      setTexts((prev) => ({ ...prev, [n]: t }));
      store.edit(n, t);
    },
    [store],
  );

  useEffect(() => {
    const known = new Set(linesRef.current.map((l) => l.line_number));
    const kept = takeStash(id).filter((e) => known.has(e.line_number));
    kept.forEach((e) => setText(e.line_number, e.translated_text));
    // The keepalive save usually got there first; only text the server lacks is news.
    const lost = kept.filter((e) => linesRef.current.find((l) => l.line_number === e.line_number)?.translated_text !== e.translated_text);
    if (lost.length) setRestored(lost.length);
    const onHide = () => {
      stash(id, store.unsaved());
      store.flushOnExit();
    };
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (store.pending()) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    const onVisibility = () => {
      if (document.visibilityState === "hidden") onHide();
    };
    window.addEventListener("pagehide", onHide);
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => {
      window.removeEventListener("pagehide", onHide);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("beforeunload", onBeforeUnload);
      const written = store.unsaved();
      stash(id, written);
      void store.flush().then(() => {
        if (!store.unsaved().length) clearStashIf(id, written);
      });
    };
  }, [id, store, setText]);

  // A failed save tries again by itself, sooner when the browser says it is back online.
  // A refusal (a 404, a 422, ...) would only be refused again, so it waits for an edit.
  useEffect(() => {
    if (save.state === "saved") {
      retries.current = 0;
      permanent.current = false;
    }
    if (save.state !== "error" || permanent.current) return;
    const retry = () => void store.flush();
    const timer = setTimeout(retry, Math.min(2000 * 2 ** retries.current++, 30_000));
    window.addEventListener("online", retry);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("online", retry);
    };
  }, [save.state, store]);

  useEffect(() => {
    void call(api.PUT("/settings", { body: { last_document_id: id } })).catch(() => {});
  }, [id]);

  useEffect(() => {
    const line = lines[active];
    if (!line) return;
    const timer = setTimeout(() => {
      void call(api.PATCH("/documents/{document_id}", {
        params: { path: { document_id: id } },
        body: { last_position: line.line_number },
      })).catch(() => {});
    }, 1000);
    return () => clearTimeout(timer);
  }, [id, lines, active]);

  const activate = useCallback((i: number | null) => {
    if (i === null) return;
    setActive(i);
    setParse(-1);
    setRestored(0);
  }, []);

  return { store, save, savePermanent: permanent.current, active, activate, parse, setParse, texts, setText, missing, restored };
}
