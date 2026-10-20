import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, call } from "../api/client";
import type { SeriesRow } from "./shelf";
import { invalidateLibrary } from "./queries";
import { postForm } from "./upload";

/** New document from pasted text, or import a desktop ---SEPERATOR--- TXT file. */
export default function NewDocument({ series, onDone }: { series: SeriesRow[]; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const [seriesId, setSeriesId] = useState("");
  const [rawText, setRawText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const fetchUrl = useMutation({
    mutationFn: () => call(api.POST("/scrape/syosetu", { body: { url: url.trim() } })),
    onSuccess: (fetched) => {
      setTitle((t) => t || fetched.title);
      setRawText(fetched.content);
      setSourceUrl(url.trim());
    },
  });
  const create = useMutation({
    mutationFn: async () => {
      const series_id = Number(seriesId);
      if (!file) {
        return call(api.POST("/documents", { body: { title, series_id, raw_text: rawText, chapter_title: "", source_language: "ja", source_url: sourceUrl } }));
      }
      const form = new FormData();
      form.append("file", file);
      if (title.trim()) form.append("title", title);
      form.append("series_id", String(series_id));
      return postForm("/documents/import/txt", form);
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
        <select value={seriesId} required onChange={(e) => setSeriesId(e.target.value)}>
          <option value="" disabled>Choose a series…</option>
          {series.map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
        </select>
      </label>
      <div className="toolbar">
        <label>
          Fetch from URL <input type="url" aria-label="Syosetu URL" value={url} disabled={!!file}
            onChange={(e) => setUrl(e.target.value)} />
        </label>
        <button type="button" disabled={!url.trim() || !!file || fetchUrl.isPending}
          onClick={() => fetchUrl.mutate()}>Fetch</button>
      </div>
      {fetchUrl.isError && <p className="error" role="alert">{fetchUrl.error.message}</p>}
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
