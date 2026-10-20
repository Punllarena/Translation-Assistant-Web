import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, call } from "../api/client";
import { Modal } from "../ui/Dialog";
import type { Doc } from "./shelf";
import { invalidateLibrary, useSeriesList } from "./queries";
import { postForm } from "./upload";

/** New chapter from pasted text, or import a desktop ---SEPERATOR--- TXT file, in a dialog. The
 *  series is preset; a preset volume receives the chapter at its end (unless the series changes). */
export default function NewDocument({ seriesId: presetSeries, volumeId, onClose }: {
  seriesId: number; volumeId: number | null; onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const series = useSeriesList();
  const [title, setTitle] = useState("");
  const [seriesId, setSeriesId] = useState(String(presetSeries));
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
      let doc: { id: number };
      if (!file) {
        doc = await call(api.POST("/documents", { body: { title, series_id, raw_text: rawText, chapter_title: "", source_language: "ja", source_url: sourceUrl } }));
      } else {
        const form = new FormData();
        form.append("file", file);
        if (title.trim()) form.append("title", title);
        form.append("series_id", String(series_id));
        doc = await postForm<Doc>("/documents/import/txt", form);
      }
      if (volumeId !== null && series_id === presetSeries) {
        await call(api.POST("/volumes/{volume_id}/documents", {
          params: { path: { volume_id: volumeId } }, body: { document_ids: [doc.id] },
        }));
      }
    },
    onSettled: () => invalidateLibrary(queryClient),
    onSuccess: onClose,
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!create.isPending) create.mutate();
  };
  return (
    <Modal title="New chapter" onClose={onClose} busy={create.isPending} onSubmit={submit}>
      <div className="dlg-head"><h2>New chapter</h2></div>
      <div className="dlg-body">
        <label className="field"><span>Title</span>
          <input value={title} required={!file} onChange={(e) => setTitle(e.target.value)} />
        </label>
        <label className="field"><span>Series</span>
          <select value={seriesId} required onChange={(e) => setSeriesId(e.target.value)}>
            {(series.data ?? []).map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
          </select>
        </label>
        <div className="toolbar">
          <label className="field"><span>Fetch from URL</span>
            <input type="url" aria-label="Syosetu URL" value={url} disabled={!!file} onChange={(e) => setUrl(e.target.value)} />
          </label>
          <button type="button" disabled={!url.trim() || !!file || fetchUrl.isPending}
            onClick={() => fetchUrl.mutate()}>Fetch</button>
        </div>
        {fetchUrl.isError && <p className="error" role="alert">{fetchUrl.error.message}</p>}
        <label className="field"><span>Source text</span>
          <textarea rows={8} value={rawText} disabled={!!file} onChange={(e) => setRawText(e.target.value)} />
        </label>
        <label className="field"><span>…or import a TXT file</span>
          <input type="file" accept=".txt,text/plain" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </label>
        {create.isError && <p className="error" role="alert">{create.error.message}</p>}
      </div>
      <div className="dlg-foot">
        <button type="button" disabled={create.isPending} onClick={onClose}>Cancel</button>
        <button type="submit" className="primary" disabled={create.isPending}>{file ? "Import" : "Create"}</button>
      </div>
    </Modal>
  );
}
