import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { api, call } from "../api/client";
import type { components } from "../api/schema";

type Entry = components["schemas"]["RunLogEntry"];

const POLL_MS = 2000;
const time = (iso: string) => new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });

/** An Ollama run's log (GET /ollama/runs/{id}/log), polled for new entries while `live`. It
 * follows the bottom unless the user has scrolled up. */
export default function RunLog({ jobId, live }: { jobId: number; live: boolean }) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [now, setNow] = useState<string | null>(null);
  const [kept, setKept] = useState(true);
  const [error, setError] = useState("");
  const box = useRef<HTMLOListElement>(null);
  const pinned = useRef(true);
  useEffect(() => {
    let after = 0;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    setEntries([]);
    setNow(null);
    setKept(true);
    setError("");
    const load = async () => {
      try {
        const r = await call(api.GET("/ollama/runs/{job_id}/log", { params: { path: { job_id: jobId }, query: { after } } }));
        if (stopped) return;
        setError("");
        setKept(r.kept);
        if (r.entries.length) setEntries((old) => [...old, ...r.entries].slice(-500));
        setNow(r.now ?? null);
        after = r.next;
        if (r.ended) return;
      } catch (e) {
        if (stopped) return;
        setError((e as Error).message);
      }
      if (live) timer = setTimeout(load, POLL_MS);
    };
    void load();
    return () => { stopped = true; clearTimeout(timer); };
  }, [jobId, live]);
  useLayoutEffect(() => {
    const el = box.current;
    if (el && pinned.current) el.scrollTop = el.scrollHeight;
  }, [entries, now]);
  const onScroll = () => {
    const el = box.current;
    if (el) pinned.current = el.scrollTop + el.clientHeight >= el.scrollHeight - 8;
  };
  if (!kept) return <p className="hint">No log for this run: the log lives in the server's memory, and the server has restarted since.</p>;
  return (
    <div className="run-log">
      <ol ref={box} role="log" aria-label="Run log" onScroll={onScroll}>
        {entries.map((e) => (
          <li key={e.seq} className={e.level}><time dateTime={e.at}>{time(e.at)}</time><span>{e.text}</span></li>
        ))}
        {now && <li className="now"><time aria-hidden="true">…</time><span>{now}</span></li>}
        {!entries.length && !now && <li className="hint"><span>{live ? "Starting…" : "Nothing was logged."}</span></li>}
      </ol>
      {error && <p className="error" role="alert">{error}</p>}
    </div>
  );
}
