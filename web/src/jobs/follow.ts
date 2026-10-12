import type { components } from "../api/schema";

export type Job = components["schemas"]["JobOut"];

const TERMINAL = new Set(["done", "failed", "cancelled"]);

export const isTerminal = (job: Job): boolean => TERMINAL.has(job.state);

/** Follow a job over SSE; closes itself on a terminal state or error. Returns a close function. */
export function followJob(id: number, onJob: (job: Job) => void, Source = EventSource): () => void {
  const source = new Source(`/api/jobs/${id}/events`);
  source.addEventListener("job", (e) => {
    let job: Job;
    try { job = JSON.parse((e as MessageEvent).data); } catch { return; }
    onJob(job);
    if (isTerminal(job)) source.close();
  });
  // EventSource would reconnect forever; the job can be re-read after a reload instead.
  source.onerror = () => source.close();
  return () => source.close();
}
