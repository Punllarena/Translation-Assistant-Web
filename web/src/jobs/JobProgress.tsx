import { useEffect, useRef, useState } from "react";
import { api, call } from "../api/client";
import { followJob, isTerminal, type Job } from "./follow";

interface FetchResult {
  added?: number;
  skipped?: number;
  missing?: number[];
  errors?: { num: number; message: string }[];
}

/** Follows one job over SSE: a progress bar, Cancel, then the outcome. */
export default function JobProgress({ jobId, onDone }: { jobId: number; onDone?: (job: Job) => void }) {
  const [job, setJob] = useState<Job | null>(null);
  const [cancelError, setCancelError] = useState("");
  const [cancelling, setCancelling] = useState(false);
  const [lost, setLost] = useState(false);
  const done = useRef(onDone);
  done.current = onDone;
  useEffect(() => {
    let finished = false;
    setJob(null);
    setLost(false);
    return followJob(jobId, (j) => {
      setJob(j);
      if (isTerminal(j) && !finished) {
        finished = true;
        done.current?.(j);
      }
    }, EventSource, () => setLost(true));
  }, [jobId]);
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
    return <p className="error" role="alert">Connection lost — reload to resume.</p>;
  }
  if (!job) return <p className="muted">Starting…</p>;
  if (!isTerminal(job)) {
    return (
      <div className="stack">
        <label>
          {job.message || "Working…"}{" "}
          <progress max={job.total || undefined} value={job.progress} />
        </label>
        <div className="toolbar"><button type="button" disabled={cancelling} onClick={cancel}>Cancel</button></div>
        {cancelError && <p className="error" role="alert">{cancelError}</p>}
      </div>
    );
  }
  if (job.state === "failed") return <p className="error" role="alert">{job.message || "The job failed"}</p>;
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
