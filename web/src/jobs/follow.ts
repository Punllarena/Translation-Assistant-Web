import type { components } from "../api/schema";

export type Job = components["schemas"]["JobOut"];

const TERMINAL = new Set(["done", "failed", "cancelled"]);

export const isTerminal = (job: Job): boolean => TERMINAL.has(job.state);

/** Follow a job over SSE; closes itself on a terminal state or error. Returns a close function. */
export function followJob(id: number, onJob: (job: Job) => void, Source = EventSource, onError: () => void = () => {}): () => void {
  const source = new Source(`/api/jobs/${id}/events`);
  source.addEventListener("job", (e) => {
    let job: Job;
    try { job = JSON.parse((e as MessageEvent).data); } catch { return; }
    onJob(job);
    if (isTerminal(job)) source.close();
  });
  // EventSource would reconnect forever: close, then read the job once. A terminal job is
  // delivered as a normal update; anything else is reported through onError.
  let closed = false;
  source.onerror = () => {
    source.close();
    fetch(`/api/jobs/${id}`)
      .then((r) => (r.ok ? (r.json() as Promise<Job>) : Promise.reject(new Error("status"))))
      .then((job) => { if (closed) return; if (isTerminal(job)) onJob(job); else onError(); })
      .catch(() => { if (!closed) onError(); });
  };
  return () => { closed = true; source.close(); };
}

/** True for a mutation result that started a job: a JobOut, or a ta.db upload ({ job_id }). */
export function startsJob(data: unknown): boolean {
  if (!data || typeof data !== "object" || Array.isArray(data)) return false;
  return "job_id" in data || ("kind" in data && "state" in data);
}
