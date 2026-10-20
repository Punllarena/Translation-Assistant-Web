import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type FormEvent } from "react";
import { Link } from "react-router";
import type { Schemas } from "../api/client";
import type { SeriesRow } from "./shelf";
import { invalidateLibrary } from "./queries";
import SeriesChoice, { appendSeries, type Choice } from "./SeriesChoice";
import { postForm } from "./upload";

const CHECK_THRESHOLD = 500; // desktop _DEFAULT_CHECK_THRESHOLD
const META = [
  ["author", "Author"], ["illustrator", "Illustrator"],
  ["publisher", "Publisher"], ["identifier", "Identifier"],
] as const;
type Meta = Record<(typeof META)[number][0], string>;
const NO_META: Meta = { author: "", illustrator: "", publisher: "", identifier: "" };

/** Two steps, as the desktop ImportEpubDialog: inspect the book, then import the checked chapters. */
export default function ImportEpub({ series }: { series: SeriesRow[] }) {
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [book, setBook] = useState<Schemas["BookOut"] | null>(null);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [choice, setChoice] = useState<Choice>({ id: "", title: "" });
  const [volumeTitle, setVolumeTitle] = useState("");
  const [meta, setMeta] = useState<Meta>(NO_META);
  const current = useRef<File | null>(null); // a slow inspect of an earlier pick must not win
  const inspect = useMutation({
    mutationFn: (f: File) => {
      const form = new FormData();
      form.append("file", f);
      return postForm<Schemas["BookOut"]>("/epub/inspect", form);
    },
    onSuccess: (b, f) => {
      if (f !== current.current) return;
      setBook(b);
      setChecked(new Set(b.chapters.filter((c) => c.char_count >= CHECK_THRESHOLD || c.image_count > 0).map((c) => c.href)));
      setChoice({ id: "", title: b.title });
      setVolumeTitle(b.title);
      setMeta({ author: b.author, illustrator: b.illustrator, publisher: b.publisher, identifier: b.identifier });
    },
  });
  const run = useMutation({
    mutationFn: () => {
      const form = new FormData();
      form.append("file", file as File);
      appendSeries(form, choice);
      form.append("volume_title", volumeTitle);
      for (const [key] of META) form.append(key, meta[key]);
      book?.chapters.filter((c) => checked.has(c.href)).forEach((c) => form.append("hrefs", c.href));
      return postForm<Schemas["EpubImportOut"]>("/epub/import", form);
    },
    onSuccess: () => invalidateLibrary(queryClient),
  });
  const pick = (f: File | null) => {
    current.current = f;
    setFile(f);
    setBook(null);
    run.reset();
    if (f) inspect.mutate(f);
    else inspect.reset();
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    run.mutate();
  };
  const toggle = (href: string, on: boolean) => {
    const next = new Set(checked);
    if (on) next.add(href);
    else next.delete(href);
    setChecked(next);
  };
  const r = run.data;
  const error = (inspect.error ?? run.error)?.message.replace(/^File too large$/, "File too large (64 MB max)");
  return (
    <form className="panel sec" aria-labelledby="import-epub-h" onSubmit={submit}>
      <div className="sec-head">
        <h2 id="import-epub-h">EPUB</h2>
        {file && <span className="muted mono">{file.name}</span>}
      </div>
      <div className="inline-form">
        <label className="btn file-btn">
          {file ? "Choose another EPUB" : "Choose an EPUB file"}
          <input type="file" accept=".epub" aria-label="EPUB file" className="visually-hidden"
            onChange={(e) => pick(e.target.files?.[0] ?? null)} />
        </label>
        <span className="hint">Up to 64 MB</span>
      </div>
      {inspect.isPending && <p className="muted">Reading…</p>}
      {book && (
        <>
          <SeriesChoice series={series} value={choice} onChange={setChoice} />
          <label className="field"><span>Volume title</span><input value={volumeTitle} onChange={(e) => setVolumeTitle(e.target.value)} /></label>
          <div className="row-fields">
            {META.map(([key, label]) => (
              <label key={key} className="field"><span>{label}</span>
                <input value={meta[key]} onChange={(e) => setMeta({ ...meta, [key]: e.target.value })} />
              </label>
            ))}
          </div>
          <fieldset className="checklist">
            <legend className="field-legend"><span>Chapters</span><span className="hint">Short pages without images start unchecked</span></legend>
            {book.chapters.map((c) => (
              <label key={c.href} className={checked.has(c.href) ? "check-row" : "check-row dim"}>
                <input type="checkbox" checked={checked.has(c.href)} onChange={(e) => toggle(c.href, e.target.checked)} />
                <span className="title">{c.order}. {c.title}</span>
                <span className="muted">{c.char_count.toLocaleString()} chars{c.image_count ? ` · ${c.image_count} images` : ""}</span>
              </label>
            ))}
          </fieldset>
          <div className="inline-form">
            <button className="primary" disabled={!checked.size || run.isPending}>Import</button>
            <span className="muted">{checked.size} chapters selected · {book.chapters.length - checked.size} unchecked</span>
          </div>
        </>
      )}
      {error && <p className="error" role="alert">{error}</p>}
      {r && (
        <div className="box ok result" role="status">
          <p><b>{r.imported.length ? "Import complete." : "Import finished — nothing new imported."}</b></p>
          <p>Imported: {r.imported.length}</p>
          <p>Skipped: {r.skipped.length} (already imported)</p>
          <p>Errors: {r.errors.length}</p>
          {r.skipped.length > 0 && <p>Skipped: {r.skipped.join(", ")}</p>}
          {r.empty.length > 0 && (
            <p>No text extracted (0 lines) — these will always read as 0% translated and are omitted from EPUB export: {r.empty.join(", ")}</p>
          )}
          {r.errors.map((x) => <p key={x.title} className="error">Error: {x.title} — {x.message}</p>)}
          <p><Link to={`/series/${r.series_id}`}>Open series</Link></p>
        </div>
      )}
    </form>
  );
}
