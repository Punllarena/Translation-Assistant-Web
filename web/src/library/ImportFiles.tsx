import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import type { Schemas } from "../api/client";
import type { SeriesRow } from "./group";
import { invalidateLibrary } from "./queries";
import SeriesChoice, { appendSeries, type Choice } from "./SeriesChoice";
import { postForm } from "./upload";

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
  const submit = (e: FormEvent) => {
    e.preventDefault();
    run.mutate();
  };
  const r = run.data;
  return (
    <form className="stack" onSubmit={submit}>
      <label>
        Files <input type="file" multiple accept=".txt,.csv" aria-label="Files to import"
          onChange={(e) => setFiles([...(e.target.files ?? [])])} />
      </label>
      <SeriesChoice series={series} value={choice} onChange={setChoice} />
      <div className="toolbar">
        <button disabled={!files.length || run.isPending}>Import</button>
      </div>
      {run.isError && <p className="error" role="alert">{run.error.message}</p>}
      {r && (
        <div role="status">
          <p>Imported: {r.imported.length}</p>
          <p>Skipped: {r.skipped.length} (already exist)</p>
          <p>Errors: {r.errors.length}</p>
          {r.warnings.map((w) => <p key={w} className="muted">{w}</p>)}
          {r.skipped.length > 0 && <p>Skipped: {r.skipped.join(", ")}</p>}
          {r.errors.map((x) => <p key={x.name} className="error">{x.name} — {x.message}</p>)}
        </div>
      )}
    </form>
  );
}
