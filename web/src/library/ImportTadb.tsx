import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
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
  const send = useMutation({
    mutationFn: (file: File) => { const form = new FormData(); form.append("file", file); return postForm<Schemas["TadbUploadOut"]>("/import/tadb", form); },
    onSuccess: (u) => { setUpload(u); setDry(null); setDone(null); setRunJob(null); },
  });
  const run = useMutation({
    mutationFn: (force: boolean) => call(api.POST("/import/tadb/{upload_id}/run", { params: { path: { upload_id: upload!.upload_id } }, body: { force } })),
    onSuccess: (job) => setRunJob(job.id),
  });
  const discard = () => {
    if (upload) void call(api.DELETE("/import/tadb/{upload_id}", { params: { path: { upload_id: upload.upload_id } } }));
    setUpload(null); setDry(null);
  };
  const report = (job: Job) => (job.state === "done" ? (job.result as unknown as Report) : null);
  const error = (send.error ?? run.error)?.message.replace(/^File too large$/, "File too large (1 GB max)");
  return (
    <section className="panel sec" aria-labelledby="tadb-h">
      <div className="sec-head"><h2 id="tadb-h">Desktop library (ta.db)</h2></div>
      <p className="hint">Imports profiles, glossaries, series and chapters from the desktop app's ta.db into your account. Nothing is written until you confirm.</p>
      <label className="field"><span>ta.db file</span>
        <input type="file" accept=".db,application/x-sqlite3" aria-label="Desktop ta.db"
          disabled={send.isPending || (upload !== null && !done)} onChange={(e) => { const f = e.currentTarget.files?.[0]; if (f) send.mutate(f); }} /></label>
      {send.isPending && <p className="muted">Uploading…</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {upload && !dry && <JobProgress jobId={upload.job_id} outcome={() => null} onDone={(j) => { const r = report(j); if (r) setDry(r); else setUpload(null); }} />}
      {dry && !runJob && (
        <>
          {dry.refused ? <p className="box danger" role="status">{dry.refused}</p> : <Counts r={dry} />}
          {dry.messages.map((m) => <p key={m} className="hint">{m}</p>)}
          <div className="toolbar">
            {dry.refused
              ? <button type="button" className="primary" onClick={() => run.mutate(true)}>Import anyway</button>
              : <button type="button" className="primary" onClick={() => run.mutate(false)}>Import</button>}
            <button type="button" onClick={discard}>Discard</button>
          </div>
        </>
      )}
      {runJob && !done && <JobProgress jobId={runJob} outcome={() => null} onDone={(j) => { const r = report(j); if (r) { setDone(r); void invalidateLibrary(queryClient); } setUpload(null); }} />}
      {done && <><p className="box ok" role="status">Imported.</p><Counts r={done} /></>}
    </section>
  );
}
