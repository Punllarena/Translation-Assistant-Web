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

/** Recent progress the page saw, for the estimate and the quiet warning. `first` is the
 * oldest point in the last WINDOW_MS, so the estimate follows the current phase's rate. */
export interface Samples { first: Sample; last: Sample; key: string; points: Sample[] }

const WINDOW_MS = 30_000;

/** Starts over when the job's state or total changes (a long wait in the queue is not slow
 * progress); otherwise records a point when the count moves and drops points older than the
 * window, keeping one at or before its start. */
export function nextSamples(prev: Samples | null, job: Pick<Job, "state" | "progress" | "total">, at: number): Samples {
  const key = `${job.state}/${job.total}`;
  if (!prev || prev.key !== key) {
    const s = { at, done: job.progress };
    return { first: s, last: s, key, points: [s] };
  }
  if (prev.last.done === job.progress) return prev;
  const points = [...prev.points, { at, done: job.progress }];
  while (points.length > 2 && points[1].at <= at - WINDOW_MS) points.shift();
  return { first: points[0], last: points[points.length - 1], key, points };
}
