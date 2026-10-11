import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, ApiError, call, errorMessage } from "../api/client";
import type { SeriesRow } from "./group";
import { invalidateLibrary } from "./queries";

/** New document from pasted text, or import a desktop ---SEPERATOR--- TXT file. */
export default function NewDocument({ series, onDone }: { series: SeriesRow[]; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const [seriesId, setSeriesId] = useState("");
  const [rawText, setRawText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const create = useMutation({
    mutationFn: async () => {
      const series_id = seriesId ? Number(seriesId) : null;
      if (!file) {
        return call(api.POST("/documents", { body: { title, series_id, raw_text: rawText, chapter_title: "", source_language: "ja", source_url: "" } }));
      }
      // Multipart: built by hand, since the generated client types JSON bodies.
      const form = new FormData();
      form.append("file", file);
      if (title.trim()) form.append("title", title);
      if (series_id !== null) form.append("series_id", String(series_id));
      const response = await fetch("/api/documents/import/txt", { method: "POST", body: form });
      if (!response.ok) {
        throw new ApiError(response.status, errorMessage(await response.json().catch(() => null)));
      }
      return response.json();
    },
    onSuccess: async () => {
      await invalidateLibrary(queryClient);
      onDone();
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate();
  };
  return (
    <form className="stack" onSubmit={submit}>
      <label>
        Title <input value={title} required={!file} onChange={(e) => setTitle(e.target.value)} />
      </label>
      <label>
        Series{" "}
        <select value={seriesId} onChange={(e) => setSeriesId(e.target.value)}>
          <option value="">Unsorted</option>
          {series.map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
        </select>
      </label>
      <label>
        Source text <textarea rows={8} value={rawText} disabled={!!file}
          onChange={(e) => setRawText(e.target.value)} />
      </label>
      <label>
        …or import a TXT file <input type="file" accept=".txt,text/plain"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </label>
      <div className="toolbar">
        <button disabled={create.isPending}>{file ? "Import" : "Create"}</button>
        <button type="button" onClick={onDone}>Cancel</button>
      </div>
      {create.isError && <p className="error" role="alert">{create.error.message}</p>}
    </form>
  );
}
