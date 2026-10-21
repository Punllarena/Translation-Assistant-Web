import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, call, type Schemas } from "../api/client";
import { Modal } from "../ui/Dialog";
import { EpubFields, EpubPicker, EpubResult, epubError, useEpubBook } from "./epubBook";
import type { SeriesRow } from "./shelf";
import { invalidateLibrary } from "./queries";
import { postForm } from "./upload";

type Mode = "empty" | "epub";

/** New volume: an empty one by title, or one imported from an EPUB into this series.
 *  A clean import closes at once; one with skipped, empty or failed chapters shows its result first. */
export default function NewVolumeDialog({ series, onCreated, onClose }: {
  series: SeriesRow; onCreated: (volumeId: number) => void; onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<Mode>("empty");
  const [title, setTitle] = useState("");
  // Generated VolumeCreate marks server-defaulted fields required; the cast sends title only.
  const create = useMutation({
    mutationFn: (t: string) =>
      call(api.POST("/series/{series_id}/volumes", { params: { path: { series_id: series.id } }, body: { title: t } as Schemas["VolumeCreate"] })),
    onSuccess: async (v) => {
      await invalidateLibrary(queryClient);
      onCreated(v.id);
    },
  });
  const epub = useEpubBook({ onPick: () => run.reset() });
  const run = useMutation({
    mutationFn: () => postForm<Schemas["EpubImportOut"]>("/epub/import", epub.importForm({ id: String(series.id), title: "" })),
    onSuccess: async (r) => {
      await invalidateLibrary(queryClient);
      if (r.imported.length && !r.skipped.length && !r.empty.length && !r.errors.length) onCreated(r.volume_id);
    },
  });
  const busy = create.isPending || run.isPending;
  const r = run.data;
  const blank = title.trim() === "";
  const canImport = epub.book !== null && epub.checked.size > 0 && epub.volumeTitle.trim() !== "";
  const submit = () => {
    if (busy) return;
    if (mode === "empty") { if (!blank) create.mutate(title.trim()); }
    else if (canImport && !r) run.mutate();
  };
  const error = mode === "empty" ? create.error?.message : epubError(epub.inspect.error ?? run.error);
  return (
    <Modal title="New volume" onClose={onClose} busy={busy} onSubmit={(e) => { e.preventDefault(); submit(); }}>
      <div className="dlg-head"><h2>New volume</h2></div>
      <div className="dlg-body">
        <div className="seg" role="group" aria-label="New volume from">
          <button type="button" aria-pressed={mode === "empty"} disabled={busy || !!r} onClick={() => setMode("empty")}>Empty</button>
          <button type="button" aria-pressed={mode === "epub"} disabled={busy || !!r} onClick={() => setMode("epub")}>Import EPUB</button>
        </div>
        {mode === "empty" ? (
          <label className="field">
            <span>Volume title</span>
            <input autoFocus value={title} onChange={(e) => setTitle(e.target.value)} />
          </label>
        ) : r ? (
          <EpubResult r={r} />
        ) : (
          <>
            <EpubPicker epub={epub} disabled={busy} />
            {epub.file && <span className="muted mono">{epub.file.name}</span>}
            <EpubFields epub={epub} />
            {epub.book && (
              <span className="muted">{epub.checked.size} chapters selected · {epub.book.chapters.length - epub.checked.size} unchecked</span>
            )}
          </>
        )}
        {error && <p className="error" role="alert">{error}</p>}
      </div>
      <div className="dlg-foot">
        {r ? (
          <button type="button" className="primary" onClick={() => onCreated(r.volume_id)}>Open volume</button>
        ) : (
          <>
            <button type="button" disabled={busy} onClick={onClose}>Cancel</button>
            {mode === "empty"
              ? <button type="submit" className="primary" disabled={blank || busy}>Create</button>
              : <button type="submit" className="primary" disabled={!canImport || busy}>{run.isPending ? "Importing…" : "Import"}</button>}
          </>
        )}
      </div>
    </Modal>
  );
}
