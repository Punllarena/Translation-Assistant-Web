import { useMutation } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ReactNode } from "react";
import type { Schemas } from "../api/client";
import { appendSeries, type Choice } from "./SeriesChoice";
import { postForm } from "./upload";
import VolumeNameFields, { kindOptions, type VolumeName } from "./VolumeNameFields";
import { prefillName } from "./volumeNames";

const CHECK_THRESHOLD = 500; // desktop _DEFAULT_CHECK_THRESHOLD
const META = [
  ["author", "Author"], ["illustrator", "Illustrator"],
  ["publisher", "Publisher"], ["identifier", "Identifier"],
] as const;
type Meta = Record<(typeof META)[number][0], string>;
const NO_META: Meta = { author: "", illustrator: "", publisher: "", identifier: "" };

type VolumeRef = { kind: string; volume_index: string | null };
const NO_VOLUMES: VolumeRef[] = [];

/** The picked EPUB, its inspection, and the volume fields and chapter ticks the import sends.
 *  The name fields follow the chosen series (title and volumes) until the user edits them. */
export function useEpubBook({ onPick, onBook, seriesTitle = "", volumes = NO_VOLUMES }: {
  onPick?: () => void; onBook?: (b: Schemas["BookOut"]) => void; seriesTitle?: string; volumes?: VolumeRef[];
} = {}) {
  const [file, setFile] = useState<File | null>(null);
  const [book, setBook] = useState<Schemas["BookOut"] | null>(null);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [volumeName, setVolumeName] = useState<VolumeName>({ kind: "", index: "", subtitle: "" });
  const [meta, setMeta] = useState<Meta>(NO_META);
  const current = useRef<File | null>(null); // a slow inspect of an earlier pick must not win
  const touched = useRef(false); // the user edited the name: stop re-parsing it
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
      touched.current = false;
      setMeta({ author: b.author, illustrator: b.illustrator, publisher: b.publisher, identifier: b.identifier });
      onBook?.(b);
    },
  });
  useEffect(() => {
    if (!book || touched.current) return;
    const p = prefillName(book.title, seriesTitle, volumes);
    setVolumeName({ kind: p.kind, index: p.index ?? "", subtitle: p.subtitle });
  }, [book, seriesTitle, volumes]);
  const editName = (n: VolumeName) => {
    touched.current = true;
    setVolumeName(n);
  };
  const pick = (f: File | null) => {
    current.current = f;
    setFile(f);
    setBook(null);
    onPick?.();
    if (f) inspect.mutate(f);
    else inspect.reset();
  };
  const toggle = (href: string, on: boolean) => {
    const next = new Set(checked);
    if (on) next.add(href);
    else next.delete(href);
    setChecked(next);
  };
  const importForm = (choice: Choice) => {
    const form = new FormData();
    form.append("file", file as File);
    appendSeries(form, choice);
    form.append("volume_kind", volumeName.kind);
    form.append("volume_index", volumeName.index);
    form.append("volume_subtitle", volumeName.subtitle);
    for (const [key] of META) form.append(key, meta[key]);
    book?.chapters.filter((c) => checked.has(c.href)).forEach((c) => form.append("hrefs", c.href));
    return form;
  };
  return { file, book, checked, volumeName, setVolumeName: editName, meta, setMeta, inspect, pick, toggle, importForm };
}

export type EpubBook = ReturnType<typeof useEpubBook>;

export const epubError = (e: Error | null | undefined) => e?.message.replace(/^File too large$/, "File too large (64 MB max)");

export function EpubPicker({ epub, disabled }: { epub: EpubBook; disabled?: boolean }) {
  return (
    <>
      <div className="inline-form">
        <label className="btn file-btn">
          {epub.file ? "Choose another EPUB" : "Choose an EPUB file"}
          <input type="file" accept=".epub" aria-label="EPUB file" className="visually-hidden" disabled={disabled}
            onChange={(e) => epub.pick(e.target.files?.[0] ?? null)} />
        </label>
        <span className="hint">Up to 64 MB</span>
      </div>
      {epub.inspect.isPending && <p className="muted">Reading…</p>}
    </>
  );
}

/** Volume name, metadata and the chapter checklist of an inspected book. */
export function EpubFields({ epub, kinds = kindOptions([]) }: { epub: EpubBook; kinds?: string[] }) {
  const { book, checked, meta } = epub;
  if (!book) return null;
  return (
    <>
      <VolumeNameFields value={epub.volumeName} onChange={epub.setVolumeName} kinds={kinds} />
      <div className="row-fields">
        {META.map(([key, label]) => (
          <label key={key} className="field"><span>{label}</span>
            <input value={meta[key]} onChange={(e) => epub.setMeta({ ...meta, [key]: e.target.value })} />
          </label>
        ))}
      </div>
      <fieldset className="checklist">
        <legend className="field-legend"><span>Chapters</span><span className="hint">Short pages without images start unchecked</span></legend>
        {book.chapters.map((c) => (
          <label key={c.href} className={checked.has(c.href) ? "check-row" : "check-row dim"}>
            <input type="checkbox" checked={checked.has(c.href)} onChange={(e) => epub.toggle(c.href, e.target.checked)} />
            <span className="title">{c.order}. {c.title}</span>
            <span className="muted">{c.char_count.toLocaleString()} chars{c.image_count ? ` · ${c.image_count} images` : ""}</span>
          </label>
        ))}
      </fieldset>
    </>
  );
}

/** What an import did: counts, skipped and empty chapters, per-chapter errors. */
export function EpubResult({ r, children }: { r: Schemas["EpubImportOut"]; children?: ReactNode }) {
  return (
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
      {children}
    </div>
  );
}
