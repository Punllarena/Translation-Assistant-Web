import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, call } from "../api/client";
import JobProgress from "../jobs/JobProgress";
import type { Job } from "../jobs/follow";
import { invalidateLibrary } from "../library/queries";
import { browserZone, defaultSlot, fromLocalInput, toLocalInput } from "../time";

interface Row {
  document_id: number; title?: string; series_order?: number; scheduled_for?: string | null;
  ok: boolean; error?: string; password?: string | null; unlock_chapter_index?: number | null;
}

function Summary({ job }: { job: Job }) {
  const rows = ((job.result ?? {}) as { chapters?: Row[] }).chapters ?? [];
  const when = (r: Row) => (r.scheduled_for ? new Date(r.scheduled_for).toLocaleString() : "now");
  return (
    <>
      <p>{job.state === "cancelled" ? "Cancelled. " : ""}{rows.filter((r) => r.ok).length} / {rows.length} published.</p>
      <ul>
        {rows.map((r) => (
          <li key={r.document_id} className={r.ok ? "" : "error"}>
            {r.ok ? "✓" : "✗"} ch {r.series_order ?? "?"} {r.title ?? ""}: {r.ok ? when(r) : r.error}
            {r.password && <> — password <code>{r.password}</code></>}
            {r.unlock_chapter_index != null && <> — chapter {r.unlock_chapter_index} unlocked</>}
          </li>
        ))}
      </ul>
    </>
  );
}

/** Publish or schedule the selected chapters as one job. */
export default function BatchPublish({ ids, onClose }: { ids: number[]; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { const d = ref.current; if (d && !d.open) d.showModal(); }, []);
  const queryClient = useQueryClient();
  const prefs = useQuery({ queryKey: ["wp", "prefs"], queryFn: () => call(api.GET("/wp/prefs")) });
  const [schedule, setSchedule] = useState(true);
  const [jobId, setJobId] = useState<number | null>(null);
  const active = useQuery({
    queryKey: ["jobs", "active", "wp_publish"], gcTime: 0,
    queryFn: () => call(api.GET("/jobs", { params: { query: { active: true } } })),
  });
  const running = jobId ?? active.data?.find((j) => j.kind === "wp_publish")?.id ?? null;
  const close = () => { void invalidateLibrary(queryClient); onClose(); };
  const start = useMutation({
    mutationFn: (f: FormData) => call(api.POST("/wp/batch", { body: {
      document_ids: ids, schedule, tz: browserZone(),
      start: schedule ? fromLocalInput(String(f.get("start"))) : null,
      chapters_per_day: schedule ? Number(f.get("perday")) : 1, confirm_republish: f.get("overwrite") === "on",
    } })),
    onSuccess: (job) => setJobId(job.id),
  });
  const submit = (e: FormEvent<HTMLFormElement>) => { e.preventDefault(); start.mutate(new FormData(e.currentTarget)); };
  const p = prefs.data;
  return (
    <dialog ref={ref} onClose={onClose} aria-label="Publish / Schedule Chapters" className="stack">
      {running !== null ? (
        <JobProgress jobId={running} onDone={() => invalidateLibrary(queryClient)} outcome={(job) => <Summary job={job} />} />
      ) : p && active.isSuccess && (
        <form className="stack" onSubmit={submit}>
          <p>{ids.length} chapter(s) selected.</p>
          <label><input type="checkbox" checked={schedule} onChange={(e) => setSchedule(e.target.checked)} /> Schedule (unchecked = publish all now)</label>
          <label>Start <input type="datetime-local" name="start" disabled={!schedule} required={schedule}
            defaultValue={toLocalInput(defaultSlot(p.wp_default_schedule_time))} /></label>
          <label>Chapters per day <input type="number" name="perday" min={1} max={99} disabled={!schedule}
            defaultValue={p.wp_chapters_per_day} /></label>
          <label><input type="checkbox" name="overwrite" /> Overwrite chapters already published or scheduled</label>
          <div className="toolbar"><button disabled={start.isPending}>Start</button></div>
        </form>
      )}
      {(prefs.error ?? start.error) && <p className="error" role="alert">{(prefs.error ?? start.error)!.message}</p>}
      <div className="toolbar"><button onClick={close}>Close</button></div>
    </dialog>
  );
}
