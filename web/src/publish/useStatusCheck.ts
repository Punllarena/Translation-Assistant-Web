import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { api, call } from "../api/client";
import { invalidateLibrary } from "../library/queries";
import { browserZone } from "../time";

/** Check status sends one WordPress request per chapter, so a click checks at most this many. */
export const STATUS_CHECK_CAP = 50;

/** The selection bar's Check status: the first `STATUS_CHECK_CAP` ids one at a time through the
 *  same per-chapter route the tag uses, the table updating as each returns. A client-side loop,
 *  no job. `stop` lets the request in flight finish, then ends the run. */
export function useStatusCheck() {
  const queryClient = useQueryClient();
  const [done, setDone] = useState(0);
  const [total, setTotal] = useState(0);
  const [capped, setCapped] = useState(false);
  const [running, setRunning] = useState(false);
  const stopped = useRef(false);
  const run = (ids: number[]) => {
    if (running) return;
    const first = ids.slice(0, STATUS_CHECK_CAP);
    stopped.current = false;
    setDone(0);
    setTotal(first.length);
    setCapped(ids.length > STATUS_CHECK_CAP);
    setRunning(true);
    void (async () => {
      for (const [i, id] of first.entries()) {
        if (stopped.current) break;
        try {
          await call(api.POST("/documents/{document_id}/wp/status", {
            params: { path: { document_id: id }, query: { tz: browserZone() } },
          }));
        } catch {
          // A chapter WordPress could not answer for keeps its stored tag; the loop goes on.
        }
        await invalidateLibrary(queryClient);
        setDone(i + 1);
      }
      setRunning(false);
    })();
  };
  const stop = () => {
    stopped.current = true;
  };
  return { run, stop, done, total, capped, running };
}
