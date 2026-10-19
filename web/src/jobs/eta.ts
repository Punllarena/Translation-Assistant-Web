import type { Job } from "./follow";

/** A progress observation: when the client saw it, and the job's count then. */
export interface Sample { at: number; done: number }

const fmt = (n: number) => n.toLocaleString("en");

/** "Checking lines · 71,330 of 482,456 (15%)", or the bare message while nothing is counted. */
export function countLine(job: Pick<Job, "message" | "progress" | "total">): string {
  if (job.total <= 1) return job.message;
  const raw = Math.round((job.progress / job.total) * 100);
  const pct = job.progress < job.total ? Math.min(raw, 99) : raw; // never 100% before the end
  return `${job.message} · ${fmt(job.progress)} of ${fmt(job.total)} (${pct}%)`;
}

export function formatDuration(ms: number): string {
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s} s`;
  const min = Math.floor(s / 60);
  return min < 60 ? `${min} min` : `${Math.floor(min / 60)} h ${min % 60} min`;
}

/** Milliseconds left at the rate observed between two samples; null until 10 s of data. */
export function estimateLeft(first: Sample, last: Sample, total: number): number | null {
  const elapsed = last.at - first.at;
  const gained = last.done - first.done;
  if (total <= 1 || gained <= 0 || elapsed < 10_000) return null;
  return ((total - last.done) * elapsed) / gained;
}

export function leftText(ms: number | null): string | null {
  if (ms === null) return null;
  return ms < 60_000 ? "under a minute left" : `about ${formatDuration(ms)} left`;
}
