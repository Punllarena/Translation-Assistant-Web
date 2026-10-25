import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { api, call } from "../api/client";
import { byVolumeOrder } from "./shelf";
import { DEFAULT_TEMPLATE, render, templateError } from "./volumeNames";
import { ConfirmDialog } from "../ui/Dialog";
import { SOURCE_LABEL, STATUS_LABEL } from "./libraryQuery";
import { invalidateLibrary, useAllVolumes, useArchive } from "./queries";
import type { SeriesRow } from "./shelf";

export default function SeriesSettings({ series, chapterCount }: { series: SeriesRow; chapterCount: number }) {
  const seriesId = series.id;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const [archiving, setArchiving] = useState(false);
  const { archive, unarchive } = useArchive(seriesId);
  const [template, setTemplate] = useState(series.volume_title_template);
  const templateProblem = templateError(template);
  const volumes = useAllVolumes();
  const first = (volumes.data ?? []).filter((v) => v.series_id === seriesId).sort(byVolumeOrder)[0];
  const sample = first
    ? { kind: first.kind, index: first.volume_index, subtitle: first.subtitle }
    : { kind: "Volume", index: "1", subtitle: "Subtitle" };
  const preview = templateProblem ? null : render(template.trim() ? template : DEFAULT_TEMPLATE, { series: series.title, ...sample });
  const chapters = `${chapterCount} ${chapterCount === 1 ? "chapter" : "chapters"}`;
  const save = useMutation({
    mutationFn: (body: { title: string; original_title: string; original_author: string; author_romaji: string; syosetu_url: string; volume_title_template: string;
      status: SeriesRow["status"]; source: SeriesRow["source"] }) =>
      call(api.PATCH("/series/{series_id}", { params: { path: { series_id: seriesId } }, body })),
    onSuccess: () => invalidateLibrary(queryClient),
  });
  const remove = useMutation({
    mutationFn: () => call(api.DELETE("/series/{series_id}", { params: { path: { series_id: seriesId } } })),
    onSuccess: async () => {
      await invalidateLibrary(queryClient);
      navigate("/");
    },
  });
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    save.mutate({
      title: String(form.get("title")),
      original_title: String(form.get("original_title")),
      original_author: String(form.get("original_author")),
      author_romaji: String(form.get("author_romaji")),
      syosetu_url: String(form.get("syosetu_url")),
      volume_title_template: template.trim() ? template : "",
      status: String(form.get("status")) as SeriesRow["status"],
      source: String(form.get("source")) as SeriesRow["source"],
    });
  };
  return (
    <div className="series-sections">
      <form className="series-sections" onSubmit={submit} key={series.id}>
        <section className="panel pad">
          <h2>Details</h2>
          <div className="row-fields">
            <label className="field"><span>Title</span><input name="title" defaultValue={series.title} required /></label>
            <label className="field"><span>Japanese title</span>
              <input name="original_title" defaultValue={series.original_title} maxLength={300} /></label>
          </div>
          <div className="row-fields">
            <label className="field"><span>Author</span>
              <input name="original_author" defaultValue={series.original_author} maxLength={300} /></label>
            <label className="field"><span>Author (romaji)</span>
              <input name="author_romaji" defaultValue={series.author_romaji} maxLength={300} /></label>
          </div>
          <div className="row-fields">
            <label className="field"><span>Series URL</span>
              <input name="syosetu_url" type="url" defaultValue={series.syosetu_url} /></label>
          </div>
          <div className="row-fields">
            <label className="field"><span>Status</span>
              <select name="status" defaultValue={series.status}>
                {Object.entries(STATUS_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select></label>
            <label className="field"><span>Source</span>
              <select name="source" defaultValue={series.source}>
                {Object.entries(SOURCE_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select></label>
          </div>
        </section>
        <section className="panel pad">
          <h2>Volume titles</h2>
          <label className="field"><span>Volume title template</span>
            <input name="volume_title_template" value={template} placeholder={DEFAULT_TEMPLATE}
              onChange={(e) => setTemplate(e.target.value)} maxLength={300} aria-invalid={templateProblem !== null} />
          </label>
          <p className="hint">Placeholders: {"{series} {kind} {index} {subtitle}"}</p>
          {templateProblem && <p className="error" role="alert">{templateProblem}</p>}
          {preview && <p className="muted">Preview: {preview}</p>}
        </section>
        <div className="toolbar">
          <button disabled={save.isPending || templateProblem !== null}>Save</button>
        </div>
        {save.error && <p className="error" role="alert">{save.error.message}</p>}
      </form>
      <section className="panel pad">
        <h2>Export</h2>
        <ul className="export-list">
          <li><a href={`/api/series/${seriesId}/export/markdown?variant=plain`} download>Markdown ZIP (complete chapters only)</a></li>
          <li><a href={`/api/series/${seriesId}/export/markdown?variant=ruby`} download>Ruby Markdown ZIP (complete chapters only)</a></li>
        </ul>
      </section>
      <section className="danger-zone">
        <h2>Danger zone</h2>
        {series.archived_at
          ? <button type="button" disabled={unarchive.isPending} onClick={() => unarchive.mutate()}>Unarchive series</button>
          : <button type="button" onClick={() => { archive.reset(); setArchiving(true); }}>Archive series</button>}
        {unarchive.error && <p className="error" role="alert">{unarchive.error.message}</p>}
        <button type="button" className="danger" onClick={() => { remove.reset(); setConfirming(true); }}>Delete series</button>
      </section>
      {archiving && (
        <ConfirmDialog
          title="Archive series"
          message={`Archive "${series.title}"? It leaves the Library but keeps all its chapters. Unarchive brings it back.`}
          confirmLabel="Archive series"
          busy={archive.isPending}
          error={archive.error?.message}
          onConfirm={() => archive.mutate(undefined, { onSuccess: () => setArchiving(false) })}
          onClose={() => setArchiving(false)}
        />
      )}
      {confirming && (
        <ConfirmDialog
          title="Delete series"
          message={`Delete "${series.title}" and its ${chapters}? This can't be undone.${series.archived_at ? "" : " To hide it without losing anything, archive it instead."}`}
          secondary={series.archived_at ? undefined : { label: "Archive instead", onClick: () => { setConfirming(false); archive.reset(); setArchiving(true); } }}
          confirmLabel={`Delete series and ${chapters}`}
          danger
          busy={remove.isPending}
          error={remove.error?.message}
          onConfirm={() => remove.mutate()}
          onClose={() => setConfirming(false)}
        />
      )}
    </div>
  );
}
