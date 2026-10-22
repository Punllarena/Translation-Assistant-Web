import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, call, type Schemas } from "../api/client";
import JobProgress from "../jobs/JobProgress";
import type { Job } from "../jobs/follow";
import { invalidateLibrary } from "./queries";
import { postForm } from "./upload";

interface Report { dry_run: boolean; refused: string | null; written: Record<string, number>; skipped: Record<string, number>; already_present: Record<string, number>; messages: string[] }

function Counts({ r }: { r: Report }) {
  const rows = Object.keys({ ...r.written, ...r.skipped, ...r.already_present }).sort();
  return (
    <table>
      <thead><tr><th>Table</th><th>{r.dry_run ? "Would add" : "Added"}</th><th>Skipped</th><th>Already present</th></tr></thead>
      <tbody>{rows.map((t) => <tr key={t}><td>{t}</td><td>{r.written[t] ?? 0}</td><td>{r.skipped[t] ?? 0}</td><td>{r.already_present[t] ?? 0}</td></tr>)}</tbody>
    </table>
  );
}

/** Desktop library: upload ta.db, read the dry run, then import (spec §6). */
export default function ImportTadb() {
  const queryClient = useQueryClient();
  const [upload, setUpload] = useState<Schemas["TadbUploadOut"] | null>(null);
  const [dry, setDry] = useState<Report | null>(null);
  const [runJob, setRunJob] = useState<number | null>(null);
  const [done, setDone] = useState<Report | null>(null);
  const [failure, setFailure] = useState("");
  // Coming back to the page: the server says which ta.db job (if any) this card was showing.
  const pending = useQuery({
    queryKey: ["import", "tadb", "pending"], gcTime: 0,
    queryFn: async () => (await api.GET("/import/tadb/pending")).data ?? null,
  });
  useEffect(() => {
    const p = pending.data;
    if (!p) return;
    const dryRun = p.job.params.dry_run === true;
    setUpload({ upload_id: p.upload_id, job_id: p.job.id });
    if (dryRun && p.job.state === "done") setDry(p.job.result as unknown as Report);
    if (!dryRun) setRunJob(p.job.id);
  }, [pending.data]);
  const send = useMutation({
    mutationFn: (file: File) => { const form = new FormData(); form.append("file", file); return postForm<Schemas["TadbUploadOut"]>("/import/tadb", form); },
    onSuccess: (u) => { setFailure(""); setUpload(u); setDry(null); setDone(null); setRunJob(null); },
  });
  const run = useMutation({
    mutationFn: (force: boolean) => call(api.POST("/import/tadb/{upload_id}/run", { params: { path: { upload_id: upload!.upload_id } }, body: { force } })),
    onSuccess: (job) => setRunJob(job.id),
  });
  // Resets the card from any unfinished state (also after a lost connection). Once the
  // real run is queued its job deletes the file itself, so only an unstarted upload is deleted here.
  const discard = () => {
    if (upload && !runJob) void call(api.DELETE("/import/tadb/{upload_id}", { params: { path: { upload_id: upload.upload_id } } }));
    // A dry run still working would otherwise run on, block new uploads, and come back on reload.
    if (upload && !runJob && !dry) void call(api.POST("/jobs/{job_id}/cancel", { params: { path: { job_id: upload.job_id } } })).catch(() => {});
    setUpload(null); setDry(null); setRunJob(null); setFailure("");
  };
  const report = (job: Job) => (job.state === "done" ? (job.result as unknown as Report) : null);
  const error = (send.error ?? run.error)?.message.replace(/^File too large$/, "File too large (1 GB max; 100 MB through Cloudflare Tunnel)");
  return (
    <section className="panel sec" aria-labelledby="tadb-h">
      <div className="sec-head"><h2 id="tadb-h">Desktop library (ta.db)</h2></div>
      <p className="hint">Imports glossaries, series and chapters from the desktop app's ta.db into your account. Nothing is written until you confirm.</p>
      <label className="field"><span>ta.db file</span>
        <input type="file" accept=".db,application/x-sqlite3" aria-label="Desktop ta.db"
          disabled={send.isPending || (upload !== null && !done)} onChange={(e) => { const f = e.currentTarget.files?.[0]; if (f) send.mutate(f); }} /></label>
      {send.isPending && <p className="muted">Uploading…</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {failure && <p className="error" role="alert">{failure}</p>}
      {upload && !dry && !runJob && <JobProgress jobId={upload.job_id} outcome={() => null} onDone={(j) => { const r = report(j); if (r) setDry(r); else { setFailure(j.state === "cancelled" ? "Cancelled" : j.message || "The import check failed"); setUpload(null); } }} />}
      {dry && !runJob && (
        <>
          {dry.refused && <p className="box danger" role="status">{dry.refused}</p>}
          <Counts r={dry} />
          {dry.messages.map((m) => <p key={m} className="hint">{m}</p>)}
        </>
      )}
      {runJob && !done && <JobProgress jobId={runJob} outcome={() => null} onDone={(j) => { const r = report(j); if (r) { setDone(r); void invalidateLibrary(queryClient); } else setFailure(j.state === "cancelled" ? "Cancelled. Upload the file again to import." : j.message || "The import failed"); setUpload(null); setRunJob(null); }} />}
      {upload && !done && (
        <div className="toolbar">
          {dry && !runJob && (dry.refused
            ? <button type="button" className="primary" onClick={() => run.mutate(true)}>Import anyway</button>
            : <button type="button" className="primary" onClick={() => run.mutate(false)}>Import</button>)}
          <button type="button" onClick={discard}>Discard</button>
        </div>
      )}
      {done && <><p className="box ok" role="status">Imported.</p><Counts r={done} /></>}
    </section>
  );
}
