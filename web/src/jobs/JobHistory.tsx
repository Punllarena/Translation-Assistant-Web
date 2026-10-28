import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link } from "react-router";
import { api, call } from "../api/client";
import { countLine, formatDuration } from "./eta";
import { isTerminal, type Job } from "./follow";
import RunLog from "./RunLog";
import { ACTIVE_JOBS_KEY, jobLink } from "./RunningJobs";

const stamp = (iso: string) => new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
const num = (v: unknown) => (typeof v === "number" ? v.toLocaleString() : "0");

/** A run's counters from `result` ({lines, failed, chunks, retries, clamped, reason}); a failed run shows its message. */
function RunResult({ job }: { job: Job }) {
  const r = job.result ?? {};
  return (
    <div className="job-result">
      {job.state === "failed" && job.message && <p className="error">{job.message}</p>}
      <dl>
        <dt>Lines</dt><dd>{num(r.lines)}</dd>
        <dt>Failed lines</dt><dd>{num(r.failed)}</dd>
        <dt>Chunks</dt><dd>{num(r.chunks)}</dd>
        <dt>Retries</dt><dd>{num(r.retries)}</dd>
        <dt>Clamped</dt><dd>{num(r.clamped)}</dd>
        {typeof r.reason === "string" && r.reason && <><dt>Ended because</dt><dd>{r.reason}</dd></>}
      </dl>
    </div>
  );
}

/** A finished run that opens to its counters and log; the log is fetched on first open. */
function RunDetails({ job, head }: { job: Job; head: ReactNode }) {
  const [opened, setOpened] = useState(false);
  return (
    <details className="job-main" onToggle={(e) => { if (e.currentTarget.open) setOpened(true); }}>
      <summary>{head}</summary>
      <RunResult job={job} />
      {opened && <RunLog jobId={job.id} live={false} />}
    </details>
  );
}

/** Queued and running jobs, each with Cancel. */
export function RunningList() {
  const queryClient = useQueryClient();
  const q = useQuery({
    queryKey: ACTIVE_JOBS_KEY,
    queryFn: () => call(api.GET("/jobs", { params: { query: { active: true } } })),
    refetchInterval: 3000,
  });
  const cancel = useMutation({
    mutationFn: (id: number) => call(api.POST("/jobs/{job_id}/cancel", { params: { path: { job_id: id } } })),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ACTIVE_JOBS_KEY }),
  });
  if (q.isPending) return <p className="muted">Loading…</p>;
  if (q.isError) return <p className="error" role="alert">{q.error.message}</p>;
  if (!q.data.length) return <p className="muted">Nothing is running.</p>;
  return (
    <>
      {cancel.error && <p className="error" role="alert">{cancel.error.message}</p>}
      <ul className="job-list panel">
        {q.data.map((job) => {
          const { label, to } = jobLink(job);
          return (
            <li key={job.id}>
              <div className="job-main">
                <strong>{label}</strong>
                <span className="hint">{job.state === "queued" ? "Waiting for another job to finish" : countLine({ ...job, message: job.message || "Working…" })}</span>
                {job.total > 1 ? <progress max={job.total} value={job.progress} /> : <progress />}
                {job.kind === "ollama_run" && <RunLog jobId={job.id} live />}
              </div>
              {to && <Link to={to}>Open</Link>}
              <button type="button" disabled={cancel.isPending} onClick={() => cancel.mutate(job.id)}>
                Cancel
              </button>
            </li>
          );
        })}
      </ul>
    </>
  );
}

/** Finished jobs, newest first; an Ollama run opens to its counters. The server returns the 50 newest. */
export function JobHistory() {
  const q = useQuery({ queryKey: ["jobs", "history"], queryFn: () => call(api.GET("/jobs")) });
  if (q.isPending) return <p className="muted">Loading…</p>;
  if (q.isError) return <p className="error" role="alert">{q.error.message}</p>;
  const done = q.data.filter(isTerminal);
  if (!done.length) return <p className="muted">No finished jobs yet.</p>;
  return (
    <ul className="job-list panel">
      {done.map((job) => {
        const { label } = jobLink(job);
        const took = job.started_at && job.finished_at ? formatDuration(new Date(job.finished_at).getTime() - new Date(job.started_at).getTime()) : null;
        const head = (
          <>
            <strong>{label}</strong>
            <span className={`job-state ${job.state}`}>{job.state}</span>
            <span className="hint">{stamp(job.finished_at ?? job.created_at)}{took && ` · ${took}`}</span>
          </>
        );
        return (
          <li key={job.id}>
            {job.kind === "ollama_run" ? (
              <RunDetails job={job} head={head} />
            ) : (
              <div className="job-main">
                <div className="job-head">{head}</div>
                {job.state === "failed" && job.message && <p className="error">{job.message}</p>}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
