import { useEffect, useRef, useState, type ReactNode } from "react";
import { api, call } from "../api/client";
import { countLine, estimateLeft, formatDuration, leftText, nextSamples, type Samples } from "./eta";
import { followJob, isTerminal, type Job } from "./follow";

interface FetchResult {
  added?: number;
  skipped?: number;
  missing?: number[];
  errors?: { num: number; message: string }[];
}

const QUIET_MS = 60_000; // no progress change this long: say so, without calling it stuck

/** Follows one job over SSE: counts, elapsed time and an estimate, Cancel (unless cancellable
 * is false), then the outcome. `background` adds the "runs on the server" line. */
export default function JobProgress({ jobId, onDone, outcome, cancellable = true, background = true, lostLink }: { jobId: number; onDone?: (job: Job) => void; outcome?: (job: Job) => ReactNode; cancellable?: boolean; background?: boolean; lostLink?: ReactNode }) {
  const [job, setJob] = useState<Job | null>(null);
  const samples = useRef<Samples | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [cancelError, setCancelError] = useState("");
  const [cancelling, setCancelling] = useState(false);
  const [lost, setLost] = useState(false);
  const done = useRef(onDone);
  done.current = onDone;
  useEffect(() => {
    let finished = false;
    setJob(null);
    setLost(false);
    samples.current = null;
    return followJob(jobId, (j) => {
      setJob(j);
      samples.current = nextSamples(samples.current, j, Date.now());
      if (isTerminal(j) && !finished) {
        finished = true;
        done.current?.(j);
      }
    }, EventSource, () => setLost(true));
  }, [jobId]);
  const running = job !== null && !isTerminal(job);
  useEffect(() => {
    if (!running) return;
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(tick);
  }, [running]);
  const cancel = async () => {
    setCancelError("");
    setCancelling(true);
    try {
      await call(api.POST("/jobs/{job_id}/cancel", { params: { path: { job_id: jobId } } }));
    } catch (e) {
      setCancelError((e as Error).message);
    } finally {
      setCancelling(false);
    }
  };
  if (lost && !(job && isTerminal(job))) {
    return (
      <div className="stack">
        <p className="error" role="alert">Connection lost — reload to resume.</p>
        {lostLink && <p>{lostLink}</p>}
      </div>
    );
  }
  if (!job) return <p className="muted">Starting…</p>;
  if (!isTerminal(job)) {
    const counted = job.total > 1;
    const elapsed = job.started_at ? formatDuration(now - Date.parse(job.started_at)) : null;
    const s = samples.current;
    const left = s ? leftText(estimateLeft(s.first, s.last, job.total)) : null;
    const quiet = job.state === "running" && s && now - s.last.at >= QUIET_MS
      ? Math.floor((now - s.last.at) / 60_000) : 0;
    return (
      <div className="stack job-progress">
        <label>
          {job.state === "queued" ? "Waiting for another job to finish" : countLine({ ...job, message: job.message || "Working…" })}
          {counted ? <progress max={job.total} value={job.progress} /> : <progress />}
        </label>
        {job.state === "running" && elapsed && <p className="hint">{elapsed} elapsed{left && ` · ${left}`}</p>}
        {quiet > 0 && <p className="hint">No progress for {quiet} min. It may still be working; large steps can take a while.</p>}
        {background && <p className="hint">Runs on the server — you can leave this page and come back.</p>}
        {cancellable && <div className="toolbar"><button type="button" disabled={cancelling} onClick={cancel}>Cancel</button></div>}
        {cancelError && <p className="error" role="alert">{cancelError}</p>}
      </div>
    );
  }
  if (job.state === "failed") {
    const failure = <p className="error" role="alert">{job.message || "The job failed"}</p>;
    return outcome ? <div className="stack">{failure}<div>{outcome(job)}</div></div> : failure;
  }
  if (outcome) return <div role="status">{outcome(job)}</div>;
  const r = (job.result ?? {}) as FetchResult;
  const parts = [job.state === "cancelled" ? "Cancelled" : `Added ${r.added ?? 0} chapter(s)`];
  if (r.skipped) parts.push(`skipped ${r.skipped}`);
  if (r.missing?.length) parts.push(`missing: ${r.missing.join(", ")}`);
  return (
    <div role="status">
      <p>{parts.join(", ")}</p>
      {(r.errors ?? []).map((e) => <p key={e.num} className="error">Chapter {e.num}: {e.message}</p>)}
    </div>
  );
}
