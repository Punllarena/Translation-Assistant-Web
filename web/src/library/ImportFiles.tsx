import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import type { Schemas } from "../api/client";
import type { SeriesRow } from "./shelf";
import { invalidateLibrary } from "./queries";
import SeriesChoice, { appendSeries, type Choice } from "./SeriesChoice";
import { postForm } from "./upload";
import { acceptFiles } from "./drop";

/** Batch import of TXT files (and an optional glossary CSV) into one series. */
export default function ImportFiles({ series }: { series: SeriesRow[] }) {
  const queryClient = useQueryClient();
  const [files, setFiles] = useState<File[]>([]);
  const [choice, setChoice] = useState<Choice>({ id: "", title: "" });
  const run = useMutation({
    mutationFn: () => {
      const form = new FormData();
      files.forEach((f) => form.append("files", f));
      appendSeries(form, choice);
      return postForm<Schemas["BatchImportOut"]>("/documents/import/batch", form);
    },
    onSuccess: () => invalidateLibrary(queryClient),
  });
  const [skipped, setSkipped] = useState<string[]>([]);
  const [over, setOver] = useState(false);
  const choose = (list: File[]) => {
    const { accepted, rejected } = acceptFiles(list, [".txt", ".csv"]);
    setFiles(accepted);
    setSkipped(rejected.map((file) => file.name));
    run.reset();
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    run.mutate();
  };
  const kb = (bytes: number) => `${Math.max(1, Math.round(bytes / 1024))} KB`;
  const r = run.data;
  return (
    <form className="panel sec" aria-labelledby="import-txt-h" onSubmit={submit}>
      <h2 id="import-txt-h">TXT and CSV files</h2>
      <label className={over ? "drop over" : "drop"}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); choose([...e.dataTransfer.files]); }}>
        <span className="drop-title">Drop files here or choose them</span>
        <span className="hint">.txt chapters, plus an optional glossary .csv · up to 500 files, 12 MB per import</span>
        <input type="file" multiple accept=".txt,.csv" aria-label="Files to import" className="visually-hidden"
          onChange={(e) => choose([...(e.target.files ?? [])])} />
      </label>
      {skipped.length > 0 && (
        <p className="hint">Skipped {skipped.length} {skipped.length === 1 ? "file that is" : "files that are"} not .txt or .csv: {skipped.join(", ")}</p>
      )}
      {files.length > 0 && (
        <ul className="file-list" aria-label="Chosen files">
          {files.map((file) => <li key={file.name}><span className="mono">{file.name}</span><span className="muted">{kb(file.size)}</span></li>)}
        </ul>
      )}
      <SeriesChoice series={series} value={choice} onChange={setChoice} />
      <div className="inline-form">
        <button className="primary" disabled={!files.length || run.isPending}>Import</button>
        {files.length > 0 && <span className="muted">{files.length} {files.length === 1 ? "file" : "files"} chosen</span>}
      </div>
      {run.isError && <p className="error" role="alert">{run.error.message}</p>}
      {r && (
        <div className="box ok result" role="status">
          <p>Imported: {r.imported.length}</p>
          <p>Skipped: {r.skipped.length} (already exist)</p>
          <p>Errors: {r.errors.length}</p>
          {r.warnings.map((w) => <p key={w}>{w}</p>)}
          {r.skipped.length > 0 && <p>Skipped: {r.skipped.join(", ")}</p>}
          {r.errors.map((x) => <p key={x.name} className="error">{x.name} — {x.message}</p>)}
        </div>
      )}
    </form>
  );
}
