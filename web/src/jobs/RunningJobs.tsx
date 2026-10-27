import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { api, call } from "../api/client";
import { countLine } from "./eta";
import type { Job } from "./follow";

export const ACTIVE_JOBS_KEY = ["jobs", "active", "all"] as const;

const LABELS: Record<string, string> = {
  tadb_import: "Desktop library import",
  dict_download: "Dictionary download",
  syosetu_fetch: "Syosetu fetch",
  wp_publish: "WordPress publish",
  wp_illustrations: "Illustrations upload",
  ollama_run: "Ollama translation",
  ollama_cleanup: "Ollama clean-up",
};

/** Where a job lives, so the list can send the user back to its page. */
export function jobLink(job: Job): { label: string; to: string | null } {
  const label = LABELS[job.kind] ?? job.kind;
  const series = job.params.series_id;
  switch (job.kind) {
    case "tadb_import": return { label, to: "/import" };
    case "dict_download": return { label, to: "/admin" };
    case "wp_publish": return { label, to: "/" };
    case "ollama_run": return { label, to: "/jobs?tab=ollama" };
    case "syosetu_fetch":
    case "wp_illustrations": return { label, to: typeof series === "number" ? `/series/${series}` : null };
    default: return { label, to: null };
  }
}

/** Header button: how many of your jobs are queued or running, with a list in a popover. */
export default function RunningJobs() {
  const q = useQuery({
    queryKey: ACTIVE_JOBS_KEY,
    queryFn: () => call(api.GET("/jobs", { params: { query: { active: true } } })),
    refetchInterval: (query) => (query.state.data?.length ? 2000 : 15000),
    refetchOnWindowFocus: true,
  });
  const jobs = q.data ?? [];
  if (!jobs.length) return null;
  const close = () => document.getElementById("running-jobs")?.hidePopover();
  return (
    <>
      <button type="button" className="quiet running-jobs" popoverTarget="running-jobs">
        <span aria-hidden="true">⟳ </span>{jobs.length} running
      </button>
      <div id="running-jobs" popover="auto" className="running-jobs-list">
        <ul>
          {jobs.map((job) => {
            const { label, to } = jobLink(job);
            return (
              <li key={job.id}>
                <strong>{label}</strong>
                <span className="hint">{job.state === "queued" ? "Waiting for another job to finish" : countLine({ ...job, message: job.message || "Working…" })}</span>
                {job.total > 1 ? <progress max={job.total} value={job.progress} /> : <progress />}
                {to && <Link to={to} onClick={close}>Open</Link>}
              </li>
            );
          })}
        </ul>
        <Link to="/jobs" onClick={close}>All jobs</Link>
      </div>
    </>
  );
}
