import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, call } from "../api/client";
import { Modal } from "../ui/Dialog";
import type { Doc } from "./shelf";
import { invalidateLibrary, useSeriesList } from "./queries";
import SeriesChoice, { seriesChosen, type Choice } from "./SeriesChoice";
import { postForm } from "./upload";

/** New chapter from pasted text, or import a desktop ---SEPERATOR--- TXT file, in a dialog. The
 *  series is preset; a preset volume receives the chapter at its end (unless the series changes). */
export default function NewDocument({ seriesId: presetSeries, volumeId, onClose }: {
  seriesId: number; volumeId: number | null; onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const series = useSeriesList();
  const [title, setTitle] = useState("");
  const [choice, setChoice] = useState<Choice>({ id: String(presetSeries), title: "" });
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
  // Set once a TXT import exists: a retry after a failed volume step only repeats that step.
  const [created, setCreated] = useState<{ id: number; seriesId: number } | null>(null);
  // The preset volume applies only while the chapter stays in the preset series.
  const targetVolume = (series_id: number) => (series_id === presetSeries ? volumeId : null);
  const createDoc = async (series_id: number): Promise<{ id: number }> => {
    if (!file) {
      return call(api.POST("/documents", { body: {
        title, series_id, volume_id: targetVolume(series_id), raw_text: rawText, chapter_title: "",
        source_language: "ja", source_url: sourceUrl,
      } }));
    }
    const form = new FormData();
    form.append("file", file);
    if (title.trim()) form.append("title", title);
    form.append("series_id", String(series_id));
    return postForm<Doc>("/documents/import/txt", form);
  };
  const create = useMutation({
    mutationFn: async () => {
      let doc = created;
      if (doc === null) {
        let series_id = Number(choice.id);
        if (choice.id === "") {
          const made = await call(api.POST("/series", { body: { title: choice.title.trim(), syosetu_url: "", original_title: "", original_author: "", author_romaji: "" } }));
          series_id = made.id;
          setChoice({ id: String(made.id), title: "" }); // a retry reuses it
        }
        doc = { id: (await createDoc(series_id)).id, seriesId: series_id };
        if (!file) return; // POST /documents placed it in the volume itself
        setCreated(doc);
      }
      const volume_id = targetVolume(doc.seriesId);
      if (volume_id === null) return;
      try {
        await call(api.POST("/volumes/{volume_id}/documents", {
          params: { path: { volume_id } }, body: { document_ids: [doc.id] },
        }));
      } catch (e) {
        throw new Error(`Created, but couldn't add it to the volume: ${(e as Error).message}`);
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
        <SeriesChoice series={series.data ?? []} value={choice} onChange={setChoice}
          disabled={created !== null} />
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
        <button type="submit" className="primary" disabled={create.isPending || !seriesChosen(choice)}>
          {created !== null ? "Retry adding to volume" : file ? "Import" : "Create"}</button>
      </div>
    </Modal>
  );
}
